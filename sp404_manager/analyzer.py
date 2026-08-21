#!/usr/bin/env python3
"""
analyzer.py — Движок анализа и классификации аудио-сэмплов.
Использует librosa. Не зависит от GUI — можно переиспользовать отдельно.
"""

from pathlib import Path
import wave

from .logging_setup import get_logger, log_duration

log = get_logger(__name__)

try:
    import numpy as np
    import librosa
    HAVE_LIBROSA = True
except ImportError as exc:
    HAVE_LIBROSA = False
    # DEBUG, а не WARNING: librosa опциональна (см. requirements.txt),
    # приложение штатно работает и без неё — это не ошибка пользователя.
    log.debug("librosa недоступна, анализ ограничен базовым (wave): %s", exc)


SUPPORTED_EXT = {".wav", ".aif", ".aiff", ".mp3", ".flac", ".ogg"}

# Метаданные категорий: иконка, цвет, человекочитаемое имя
CATEGORY_META = {
    "kick":       {"icon": "🥁", "color": "#e63946", "label": "Kick"},
    "snare":      {"icon": "🪘", "color": "#f77f00", "label": "Snare"},
    "hihat":      {"icon": "🎩", "color": "#fcbf49", "label": "Hi-Hat"},
    "clap":       {"icon": "👏", "color": "#c9b458", "label": "Clap"},
    "perc":       {"icon": "🪗", "color": "#d62828", "label": "Perc"},
    "bass":       {"icon": "🎸", "color": "#4361ee", "label": "Bass"},
    "melody":     {"icon": "🎹", "color": "#2a9d8f", "label": "Melody"},
    "loop_drum":  {"icon": "🔁", "color": "#8338ec", "label": "Drum Loop"},
    "loop_music": {"icon": "🎼", "color": "#3a86ff", "label": "Music Loop"},
    "fx":         {"icon": "🌊", "color": "#06d6a0", "label": "FX"},
    "vocal":      {"icon": "🎤", "color": "#ef476f", "label": "Vocal"},
    "unknown":    {"icon": "❓", "color": "#6c757d", "label": "Unknown"},
}

# Порядок категорий для авто-раскладки по банкам
CATEGORY_ORDER = ["kick", "snare", "hihat", "clap", "perc", "bass",
                  "melody", "vocal", "fx", "loop_drum", "loop_music", "unknown"]


def get_duration_basic(filepath: Path) -> float:
    """Длительность WAV без librosa."""
    try:
        with wave.open(str(filepath), "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception as exc:
        # Фолбэк по умолчанию (0.0) уже не отличить от «файл пуст» —
        # причина хотя бы остаётся в логе.
        log.warning("Не удалось определить длительность %s: %s",
                    filepath.name, exc)
        return 0.0


def analyze_sample(filepath: Path) -> dict:
    """
    Анализирует аудиофайл и возвращает:
    { category, duration, tempo, analyzed, [error] }
    """
    filepath = Path(filepath)
    if not HAVE_LIBROSA:
        result = {"category": "unknown",
                  "duration": round(get_duration_basic(filepath), 3),
                  "tempo": 0.0, "analyzed": False}
        log.debug("Анализ %s пропущен (нет librosa), только длительность",
                  filepath.name)
        return result
    try:
        y, sr = librosa.load(str(filepath), sr=None, mono=True, duration=30.0)
    except Exception as e:
        # Битый файл, неподдерживаемый кодек, поврежденный заголовок —
        # раньше это тонуло в тихом "analyzed: False", ошибка уходила
        # в поле error, но нигде не логировалась.
        log.warning("Не удалось загрузить %s для анализа: %s: %s",
                    filepath.name, type(e).__name__, e)
        return {"category": "unknown", "duration": 0.0, "tempo": 0.0,
                "analyzed": False, "error": str(e)}

    # Извлечение признаков не оборачиваем в try/except: если librosa
    # упадёт здесь (например, на вырожденном сигнале), исключение должно
    # дойти до вызывающего кода как и раньше — log_duration лишь добавляет
    # запись в лог с traceback перед тем как пробросить его дальше.
    with log_duration(log, "анализ сэмпла", file=filepath.name):
        duration = librosa.get_duration(y=y, sr=sr)
        stft = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sr)

        cent = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
        zcr = float(np.mean(librosa.feature.zero_crossing_rate(y)))

        def band(f_lo, f_hi):
            idx = np.where((freqs >= f_lo) & (freqs < f_hi))[0]
            return float(np.mean(stft[idx, :] ** 2)) if len(idx) else 0.0

        e_lo = band(20, 300); e_mid = band(300, 3000)
        e_hi = band(3000, 8000); e_air = band(8000, 20000)
        tot = e_lo + e_mid + e_hi + e_air + 1e-10
        r_lo, r_mid, r_hi = e_lo / tot, e_mid / tot, e_hi / tot

        rms = librosa.feature.rms(y=y)[0]
        peak_t = int(np.argmax(rms)) * 512 / sr
        decay = float(np.mean(rms[len(rms) // 2:])) / (float(np.mean(rms)) + 1e-10)

        try:
            tempo = float(librosa.beat.beat_track(y=y, sr=sr)[0])
        except Exception as e:
            # Не критично: детекция темпа регулярно не срабатывает на
            # коротких/шумных сэмплах (kick, hi-hat) — это ожидаемо,
            # а не ошибка пользователя, поэтому DEBUG, а не WARNING.
            log.debug("BPM для %s не определён: %s", filepath.name, e)
            tempo = 0.0
        beats = float(np.mean(librosa.onset.onset_strength(y=y, sr=sr)))
        harm = librosa.effects.hpss(y)[0]
        harm_r = float(np.mean(np.abs(harm))) / (float(np.mean(np.abs(y))) + 1e-10)
        chroma_v = float(np.var(librosa.feature.chroma_stft(y=y, sr=sr)))

        feats = dict(duration=duration, cent=cent, zcr=zcr, r_lo=r_lo, r_mid=r_mid,
                     r_hi=r_hi, peak_t=peak_t, decay=decay, tempo=tempo,
                     beats=beats, harm=harm_r, chroma=chroma_v)
        category = _classify(feats)
        result = {
            "category": category,
            "duration": round(duration, 3),
            "tempo": round(tempo, 1),
            "analyzed": True,
        }

    log.debug("Готово: %s -> %s (%.2fс, %.1f BPM)",
              filepath.name, category, duration, tempo)
    return result


def _classify(f) -> str:
    """Дерево решений на основе акустических признаков."""
    dur, cent, zcr = f["duration"], f["cent"], f["zcr"]
    r_lo, r_mid, r_hi = f["r_lo"], f["r_mid"], f["r_hi"]
    peak_t, decay, harm, chroma = f["peak_t"], f["decay"], f["harm"], f["chroma"]
    tempo, beats = f["tempo"], f["beats"]
    short, vshort, long_ = dur < 2.0, dur < 0.5, dur > 4.0
    fast_att, fast_dec = peak_t < 0.05, decay < 0.5

    if long_ and tempo > 60 and beats > 1.5 and harm < 0.6: return "loop_drum"
    if long_ and harm > 0.5 and chroma > 0.015:             return "loop_music"
    if dur > 2.5 and harm > 0.6 and chroma > 0.02:          return "loop_music"
    if harm > 0.7 and chroma > 0.04 and 800 < cent < 4000 and not vshort and r_mid > 0.45 and zcr < 0.08:
        return "vocal"
    if cent < 1500 and r_lo > 0.5 and fast_att and short and fast_dec: return "kick"
    if cent < 800 and r_lo > 0.6 and short:                 return "kick"
    if cent > 5000 and r_hi > 0.45 and zcr > 0.2:           return "hihat"
    if cent > 4000 and r_hi > 0.55 and vshort:              return "hihat"
    if short and 2000 < cent < 6000 and r_mid > 0.35 and zcr > 0.1 and fast_att: return "clap"
    if short and 1500 < cent < 5000 and r_mid > 0.35 and fast_att: return "snare"
    if short and beats > 1.2 and fast_att and harm < 0.5:   return "perc"
    if cent < 800 and r_lo > 0.55:                          return "bass"
    if harm > 0.55 and chroma > 0.025 and cent > 500:       return "melody"
    if harm > 0.6 and not short:                            return "melody"
    if zcr > 0.15 and harm < 0.3 and chroma < 0.01:         return "fx"
    if short and fast_att:                                  return "perc"
    return "unknown"


# Публичный алиас (для тестов и внешнего API)
classify = _classify
