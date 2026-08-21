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

try:
    import numpy as np
    import librosa
    HAVE_LIBROSA = True
except ImportError:
    HAVE_LIBROSA = False


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
        raise ValueError(f"Банк {bank_char} не поддерживается (только A-J)")
    record_idx = bank_idx * 12 + (pad_num - 1)
    if record_idx >= 120:
        raise ValueError(f"Пэд {pad} вне диапазона")
    return record_idx


class PadInfoRecord:
    """Одна запись (32 байта) в PADINFO.BIN."""
    
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
        self.format = 1
        self.orig_tempo = 1200       # 120 BPM × 10
        self.user_tempo = 1200
    
    def to_bytes(self) -> bytes:
        """Кодирует в 32 байта (big-endian)."""
        return struct.pack(
            ">IIII BBBBBB HH 6s",
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
            self.orig_tempo,
            self.user_tempo,
            b'\x00' * 6
        )


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
            except Exception:
                pass
    except Exception:
        pass
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
        shutil.copy2(str(src), str(dst))


def export_sd(assignments: dict, samples: dict, out_dir: Path,
              progress_cb=None, padinfo_records: dict = None) -> dict:
    """Экспортирует сэмплы и PADINFO.BIN."""
    out_dir = Path(out_dir)
    smpl_dir = out_dir / "ROLAND" / "SP-404SX" / "SMPL"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    smpl_dir.mkdir(parents=True, exist_ok=True)

    exported, errors = [], []
    items = list(assignments.items())
    total = len(items)
    
    if padinfo_records is None:
        padinfo_records = {}

    # Экспортируем WAV-файлы
    for i, (pad, sid) in enumerate(items):
        s = samples.get(sid)
        if not s:
            continue
        src = Path(s["path"])
        if not src.exists():
            errors.append(f"{pad}: файл отсутствует ({s.get('name','?')})")
            continue
        dst = smpl_dir / pad_to_filename(pad)
        try:
            convert_to_sx_wav(src, dst)
            exported.append({"pad": pad, "file": dst.name, "sample": s["name"]})
        except Exception as e:
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
                                if s.get("tempo", 0) > 0:
                                    tempo_val = int(s["tempo"] * 10)
                                    rec.orig_tempo = tempo_val
                                    rec.user_tempo = tempo_val
                            except Exception:
                                pass
                    
                    pf.write(rec.to_bytes())
    except Exception as e:
        errors.append(f"PADINFO.BIN: {e}")

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
                break
            assignments[f"{banks[b]}{p}"] = sid
        bank_idx += max(1, (len(group) + pads_per_bank - 1) // pads_per_bank)
        if bank_idx >= len(banks):
            break
    return assignments
