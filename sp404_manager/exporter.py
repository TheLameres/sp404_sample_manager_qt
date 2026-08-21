#!/usr/bin/env python3
"""
exporter.py — Экспорт назначений пэдов в структуру SD-карты SP-404SX.

Формат (см. https://athanasi.us/site/sp404_file_format.html):
  ROLAND/SP-404SX/SMPL/A0000001.WAV  — сэмплы
  ROLAND/SP-404SX/SMPL/PADINFO.BIN   — метаданные пэдов (120 × 32 байта)

PADINFO.BIN структура (big-endian):
  120 записей (A1-J12), каждая 32 байта
"""

import shutil
import struct
import wave
from pathlib import Path

from .logging_setup import get_logger, log_duration

log = get_logger(__name__)

try:
    import numpy as np
    import librosa
    HAVE_LIBROSA = True
except ImportError as exc:
    HAVE_LIBROSA = False
    log.debug("librosa недоступна, экспорт будет копировать файлы без "
              "конвертации в 44.1kHz/16-bit: %s", exc)


def pad_to_filename(pad: str) -> str:
    """'A1' -> 'A0000001.WAV'"""
    bank = pad[0]
    num = int(pad[1:])
    return f"{bank}{num:07d}.WAV"


def pad_to_padinfo_index(pad: str) -> int:
    """Индекс записи в PADINFO.BIN (A1-J12, 120 записей)."""
    bank_char = pad[0]
    pad_num = int(pad[1:])
    bank_idx = ord(bank_char) - ord('A')
    if bank_idx >= 10:
        msg = f"Банк {bank_char} не поддерживается (только A-J)"
        log.error(msg)
        raise ValueError(msg)
    record_idx = bank_idx * 12 + (pad_num - 1)
    if record_idx >= 120:
        msg = f"Пэд {pad} вне диапазона"
        log.error(msg)
        raise ValueError(msg)
    return record_idx


class PadInfoRecord:
    """Одна запись (32 байта) в PADINFO.BIN.

    Бинарная раскладка (big-endian), согласно спецификации
    https://gist.github.com/threedaymonk/701ca30e5d363caa288986ad972ab3e0
    и уттори-парсеру uttori-audio-padinfo:

        offset  поле              тип
        0       orig_sample_start uint32
        4       orig_sample_end   uint32
        8       user_sample_start uint32
        12      user_sample_end   uint32
        16      volume            uint8   (0-127)
        17      lofi              uint8   (0/1)
        18      loop              uint8   (0/1)
        19      gate              uint8   (0/1)
        20      reverse           uint8   (0/1)
        21      format            uint8   (0=AIFF, 1=WAVE)
        22      channels          uint8   (1=mono, 2=stereo)
        23      tempo_mode        uint8   (0=Off, 1=Pattern, 2=User)
        24      orig_tempo        uint32  (BPM × 10)
        28      user_tempo        uint32  (BPM × 10)

    Итого 32 байта. ВАЖНО: OrigTempo/UserTempo — это uint32, а не uint16,
    как было в предыдущей (ошибочной) реализации — старый код упаковывал
    tempo как два uint16 + 6 нулевых байт, из-за чего реальные значения
    BPM попадали в поля Channels/TempoMode и OrigTempo/UserTempo читались
    как мусор при разборе по спецификации.
    """

    #: struct-формат одной записи (32 байта, big-endian)
    STRUCT_FMT = ">IIII BBBBBBBB II"

    # Допустимые диапазоны для валидации
    MIN_BPM = 20.0
    MAX_BPM = 300.0

    def __init__(self):
        self.orig_sample_start = 512
        self.orig_sample_end = 512 + 44100
        self.user_sample_start = 512
        self.user_sample_end = 512 + 44100
        self.volume = 127
        self.lofi = 0
        self.loop = 0
        self.gate = 1
        self.reverse = 0
        self.format = 1              # 1 = WAVE (проект всегда экспортирует WAV)
        self.channels = 2            # 1 = mono, 2 = stereo
        self.tempo_mode = 0          # 0=Off, 1=Pattern, 2=User
        self.orig_tempo = 1200       # 120 BPM × 10
        self.user_tempo = 1200

    def validate(self) -> None:
        """Проверяет диапазоны полей перед упаковкой. Бросает ValueError."""
        def _check_bit(name, value):
            if value not in (0, 1):
                raise ValueError(f"{name} должен быть 0 или 1, получено {value!r}")

        if not (0 <= self.volume <= 127):
            raise ValueError(f"volume должен быть в диапазоне 0-127, получено {self.volume!r}")
        _check_bit("lofi", self.lofi)
        _check_bit("loop", self.loop)
        _check_bit("gate", self.gate)
        _check_bit("reverse", self.reverse)
        if self.format not in (0, 1):
            raise ValueError(f"format должен быть 0 (AIFF) или 1 (WAVE), получено {self.format!r}")
        if self.channels not in (1, 2):
            raise ValueError(f"channels должен быть 1 (mono) или 2 (stereo), получено {self.channels!r}")
        if self.tempo_mode not in (0, 1, 2):
            raise ValueError(f"tempo_mode должен быть 0/1/2 (Off/Pattern/User), получено {self.tempo_mode!r}")
        for name, tempo in (("orig_tempo", self.orig_tempo), ("user_tempo", self.user_tempo)):
            bpm = tempo / 10.0
            if not (self.MIN_BPM <= bpm <= self.MAX_BPM):
                raise ValueError(
                    f"{name}={tempo} ({bpm} BPM) вне диапазона "
                    f"{self.MIN_BPM}-{self.MAX_BPM} BPM"
                )
        for name in ("orig_sample_start", "orig_sample_end",
                     "user_sample_start", "user_sample_end"):
            value = getattr(self, name)
            if not (0 <= value <= 0xFFFFFFFF):
                raise ValueError(f"{name}={value} вне диапазона uint32")

    def set_bpm(self, bpm: float, mode: str = "user") -> None:
        """Устанавливает BPM. mode: 'user' — только user_tempo,
        'orig' — только orig_tempo, 'both' — оба поля."""
        if not (self.MIN_BPM <= bpm <= self.MAX_BPM):
            raise ValueError(f"bpm={bpm} вне диапазона {self.MIN_BPM}-{self.MAX_BPM}")
        tempo_val = round(bpm * 10)
        if mode not in ("user", "orig", "both"):
            raise ValueError("mode должен быть 'user', 'orig' или 'both'")
        if mode in ("user", "both"):
            self.user_tempo = tempo_val
        if mode in ("orig", "both"):
            self.orig_tempo = tempo_val

    def to_bytes(self) -> bytes:
        """Кодирует в 32 байта (big-endian)."""
        self.validate()
        return struct.pack(
            self.STRUCT_FMT,
            self.orig_sample_start,
            self.orig_sample_end,
            self.user_sample_start,
            self.user_sample_end,
            self.volume,
            self.lofi,
            self.loop,
            self.gate,
            self.reverse,
            self.format,
            self.channels,
            self.tempo_mode,
            self.orig_tempo,
            self.user_tempo,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "PadInfoRecord":
        """Разбирает 32 байта записи PADINFO.BIN в PadInfoRecord."""
        expected_size = struct.calcsize(cls.STRUCT_FMT)
        if len(data) != expected_size:
            raise ValueError(
                f"Ожидалось {expected_size} байт на запись, получено {len(data)}"
            )
        (orig_start, orig_end, user_start, user_end,
         volume, lofi, loop, gate, reverse, fmt,
         channels, tempo_mode, orig_tempo, user_tempo) = struct.unpack(cls.STRUCT_FMT, data)

        rec = cls()
        rec.orig_sample_start = orig_start
        rec.orig_sample_end = orig_end
        rec.user_sample_start = user_start
        rec.user_sample_end = user_end
        rec.volume = volume
        rec.lofi = lofi
        rec.loop = loop
        rec.gate = gate
        rec.reverse = reverse
        rec.format = fmt
        rec.channels = channels
        rec.tempo_mode = tempo_mode
        rec.orig_tempo = orig_tempo
        rec.user_tempo = user_tempo
        return rec


#: Число записей в PADINFO.BIN и размер каждой записи в байтах
PADINFO_RECORD_COUNT = 120
PADINFO_RECORD_SIZE = struct.calcsize(PadInfoRecord.STRUCT_FMT)


def padinfo_index_to_pad(index: int) -> str:
    """Обратное преобразование индекса записи (0-119) в идентификатор пэда 'A1'-'J12'."""
    if not (0 <= index < PADINFO_RECORD_COUNT):
        raise ValueError(f"index={index} вне диапазона 0-{PADINFO_RECORD_COUNT - 1}")
    bank_idx, pad_num = divmod(index, 12)
    bank_char = chr(ord('A') + bank_idx)
    return f"{bank_char}{pad_num + 1}"


def parse_padinfo(path: Path) -> dict:
    """Читает существующий PADINFO.BIN и возвращает {pad_id: PadInfoRecord}.

    Ожидается файл из ровно PADINFO_RECORD_COUNT записей по
    PADINFO_RECORD_SIZE байт каждая (итого 120 × 32 = 3840 байт).
    """
    path = Path(path)
    data = path.read_bytes()
    expected_size = PADINFO_RECORD_COUNT * PADINFO_RECORD_SIZE
    if len(data) != expected_size:
        log.warning(
            "PADINFO.BIN %s: ожидалось %d байт (%d записей по %d), "
            "получено %d — файл может быть повреждён или из другой модели",
            path, expected_size, PADINFO_RECORD_COUNT, PADINFO_RECORD_SIZE, len(data)
        )

    records = {}
    n_records = len(data) // PADINFO_RECORD_SIZE
    for i in range(min(n_records, PADINFO_RECORD_COUNT)):
        chunk = data[i * PADINFO_RECORD_SIZE:(i + 1) * PADINFO_RECORD_SIZE]
        pad_id = padinfo_index_to_pad(i)
        try:
            records[pad_id] = PadInfoRecord.from_bytes(chunk)
        except Exception:
            log.exception("Не удалось разобрать запись PADINFO для пэда %s", pad_id)
    return records


def estimate_sample_frames(filepath: Path) -> tuple:
    """Оценивает (start, end) frames для PADINFO."""
    try:
        if HAVE_LIBROSA:
            y, sr = librosa.load(str(filepath), sr=44100, mono=True)
            return (512, 512 + len(y))
        else:
            try:
                with wave.open(str(filepath), "rb") as w:
                    frames = w.getnframes()
                    return (512, 512 + frames)
            except Exception as exc:
                log.warning("Не удалось прочитать длину %s (wave): %s — "
                            "PADINFO получит длину-заглушку 1с",
                            filepath.name, exc)
    except Exception as exc:
        log.warning("Не удалось оценить длину %s через librosa: %s — "
                    "PADINFO получит длину-заглушку 1с", filepath.name, exc)
    return (512, 512 + 44100)


def convert_to_sx_wav(src: Path, dst: Path):
    """Конвертирует аудиофайл в WAV 44.1kHz/16-bit."""
    src, dst = Path(src), Path(dst)
    if HAVE_LIBROSA:
        y, sr = librosa.load(str(src), sr=44100, mono=False)
        if y.ndim == 1:
            data = (np.clip(y, -1, 1) * 32767).astype("<i2")
            channels = 1
        else:
            y = np.clip(y, -1, 1)
            inter = np.empty((y.shape[1] * 2,), dtype="<i2")
            inter[0::2] = (y[0] * 32767).astype("<i2")
            inter[1::2] = (y[1] * 32767).astype("<i2")
            data, channels = inter, 2
        with wave.open(str(dst), "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes(data.tobytes())
    else:
        log.debug("librosa недоступна — %s копируется без конвертации "
                  "(SP-404SX может не принять формат)", src.name)
        shutil.copy2(str(src), str(dst))


def export_sd(assignments: dict, samples: dict, out_dir: Path,
              progress_cb=None, padinfo_records: dict = None) -> dict:
    """Экспортирует сэмплы и PADINFO.BIN."""
    out_dir = Path(out_dir)
    smpl_dir = out_dir / "ROLAND" / "SP-404SX" / "SMPL"

    log.info("Экспорт: %d пэдов -> %s", len(assignments), out_dir)
    if out_dir.exists():
        log.debug("Целевой каталог существует, удаляю: %s", out_dir)
        shutil.rmtree(out_dir)
    smpl_dir.mkdir(parents=True, exist_ok=True)

    exported, errors = [], []
    items = list(assignments.items())
    total = len(items)

    if padinfo_records is None:
        padinfo_records = {}

    # Экспортируем WAV-файлы
    with log_duration(log, "конвертация сэмплов", count=total):
        for i, (pad, sid) in enumerate(items):
            s = samples.get(sid)
            if not s:
                log.warning("Пэд %s ссылается на несуществующий сэмпл %s "
                            "— пропущен", pad, sid)
                continue
            src = Path(s["path"])
            if not src.exists():
                msg = f"{pad}: файл отсутствует ({s.get('name','?')})"
                log.warning(msg)
                errors.append(msg)
                continue
            dst = smpl_dir / pad_to_filename(pad)
            try:
                convert_to_sx_wav(src, dst)
                exported.append({"pad": pad, "file": dst.name, "sample": s["name"]})
            except Exception as e:
                # Конвертация — единственное, что реально портит экспорт:
                # без лога пользователь видел бы просто "ошибок: N" без
                # единого шанса понять, какой файл и почему.
                log.exception("Конвертация %s (пэд %s) не удалась",
                              s.get("name", src.name), pad)
                errors.append(f"{pad}: {e}")
            if progress_cb:
                progress_cb(i + 1, total)

    # Создаём PADINFO.BIN
    padinfo_path = smpl_dir / "PADINFO.BIN"
    try:
        with open(padinfo_path, "wb") as pf:
            for bank_idx in range(10):  # A-J
                bank_char = chr(ord('A') + bank_idx)
                for pad_num in range(1, 13):  # 1-12
                    pad_id = f"{bank_char}{pad_num}"
                    rec = PadInfoRecord()

                    if pad_id in padinfo_records:
                        custom = padinfo_records[pad_id]
                        if isinstance(custom, dict):
                            for k, v in custom.items():
                                if hasattr(rec, k):
                                    setattr(rec, k, v)
                        elif isinstance(custom, PadInfoRecord):
                            rec = custom
                    elif pad_id in assignments:
                        sid = assignments[pad_id]
                        s = samples.get(sid)
                        if s:
                            try:
                                start, end = estimate_sample_frames(Path(s["path"]))
                                rec.orig_sample_start = start
                                rec.orig_sample_end = end
                                rec.user_sample_start = start
                                rec.user_sample_end = end
                                bpm = s.get("tempo", 0)
                                if bpm and PadInfoRecord.MIN_BPM <= bpm <= PadInfoRecord.MAX_BPM:
                                    rec.set_bpm(bpm, mode="both")
                            except Exception:
                                log.warning(
                                    "Метаданные для пэда %s (%s) не "
                                    "рассчитаны, использую значения "
                                    "по умолчанию", pad_id, s.get("name", "?"),
                                    exc_info=True)

                    pf.write(rec.to_bytes())
    except Exception as e:
        # Сбой записи PADINFO.BIN — это не «ошибка одного пэда», а порча
        # структуры SD-карты целиком: SP-404SX может не увидеть ни один
        # сэмпл. Такое должно быть максимально заметно в логе.
        log.exception("Не удалось записать PADINFO.BIN — SD-карта "
                      "будет нерабочей")
        errors.append(f"PADINFO.BIN: {e}")

    log.info("Экспорт завершён: успешно=%d, ошибок=%d",
             len(exported), len(errors))
    return {
        "exported": exported,
        "errors": errors,
        "padinfo_path": str(padinfo_path),
        "smpl_dir": str(smpl_dir),
    }


def auto_assign(samples: dict, banks: list, pads_per_bank: int) -> dict:
    """Авто-раскладка по категориям."""
    from .analyzer import CATEGORY_ORDER

    by_cat = {c: [] for c in CATEGORY_ORDER}
    for sid, s in samples.items():
        by_cat.setdefault(s["category"], by_cat["unknown"]).append(sid)

    assignments = {}
    bank_idx = 0
    for cat in CATEGORY_ORDER:
        group = by_cat.get(cat, [])
        if not group:
            continue
        for i, sid in enumerate(group):
            b = bank_idx + (i // pads_per_bank)
            p = (i % pads_per_bank) + 1
            if b >= len(banks):
                # Банки закончились — оставшиеся сэмплы категории (и все
                # последующие категории) молча не получают пэд. Раньше
                # это было незаметно: счётчик "назначено" в UI просто
                # оказывался меньше числа сэмплов без единого сообщения.
                log.warning("Банки закончились: %d сэмпл(ов) категории "
                            "'%s' не поместились", len(group) - i, cat)
                break
            assignments[f"{banks[b]}{p}"] = sid
        bank_idx += max(1, (len(group) + pads_per_bank - 1) // pads_per_bank)
        if bank_idx >= len(banks):
            break

    not_placed = len(samples) - len(assignments)
    log.debug("Авто-раскладка: %d сэмплов -> %d пэдов назначено%s",
              len(samples), len(assignments),
              f", {not_placed} не поместилось" if not_placed else "")
    return assignments
