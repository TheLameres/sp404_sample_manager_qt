#!/usr/bin/env python3
"""
test_stress_gui.py — воспроизводит сценарии, ронявшие приложение на macOS:
  • drop сэмпла на пэд (эмуляция QDropEvent внутри drag-loop)
  • клик по «✕» (очистка пэда)
  • многократное переключение банков
  • авто-раскладка + очистка всех пэдов
  • удаление сэмпла, на который назначен пэд

Раньше здесь был segfault из-за пересоздания виджетов в обработчике события.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

import sys, shutil, wave
from pathlib import Path
import numpy as np

from PySide6.QtCore import Qt, QMimeData, QByteArray, QPoint, QTimer
from PySide6.QtGui import QDropEvent, QDragEnterEvent
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from sp404_manager.platform_utils import get_app_dir
import sp404_manager.main as M
from sp404_manager.main import AnalyzeWorker, MIME_SAMPLE

# чистый старт
appdir = Path(get_app_dir())
if appdir.exists():
    shutil.rmtree(appdir)
# пересоздаём рабочие папки (модуль создал их при импорте)
M.APP_DIR.mkdir(parents=True, exist_ok=True)
M.SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

# тестовые сэмплы
tdir = Path("/tmp/stress_samples")
if tdir.exists():
    shutil.rmtree(tdir)
tdir.mkdir(parents=True)
SR = 44100


def mk(p, y):
    y = np.clip(y, -1, 1)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((y * 32767).astype("<i2").tobytes())


t = np.linspace(0, 0.4, int(SR * 0.4))
mk(tdir / "kick.wav", np.sin(2 * np.pi * 60 * t) * np.exp(-t * 20))
mk(tdir / "snare.wav", np.random.randn(len(t)) * 0.4 * np.exp(-t * 15))
t2 = np.linspace(0, 2.0, int(SR * 2.0))
mk(tdir / "bass.wav", np.sin(2 * np.pi * 80 * t2) * 0.7 * np.exp(-t2 * 0.5))

win = M.MainWindow()
win.resize(1180, 780)
win.show()

# загрузка
w = AnalyzeWorker([str(f) for f in sorted(tdir.iterdir())])
w.one_done.connect(win._on_sample_added)
w.run()
sids = list(win.samples.keys())
print(f"[1] загружено сэмплов: {len(sids)}")
assert len(sids) == 3

# ── виджеты создаются один раз ──
pad_ids_before = [id(p) for p in win._pad_slots]
bank_ids_before = [id(b) for b in win.bank_btns.values()]
print(f"[2] PadWidget создано: {len(win._pad_slots)}, кнопок банков: {len(win.bank_btns)}")


def make_drop(widget, sid):
    """Эмулирует настоящий QDropEvent на пэд."""
    mime = QMimeData()
    mime.setData(MIME_SAMPLE, QByteArray(sid.encode()))
    pos = widget.rect().center()
    ev = QDropEvent(pos, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    widget.dropEvent(ev)


# ── СЦЕНАРИЙ 1: drop на пэды (то, что роняло) ──
for i, sid in enumerate(sids):
    pad = win._pad_slots[i]
    make_drop(pad, sid)
app.processEvents()          # выполняем отложенные QTimer.singleShot(0)
print(f"[3] после drop назначено пэдов: {len(win.assignments)}")
assert len(win.assignments) == 3, win.assignments

# ── СЦЕНАРИЙ 2: клик по «✕» ──
win._pad_slots[0].clear_btn.click()
app.processEvents()
print(f"[4] после очистки пэда: {len(win.assignments)}")
assert len(win.assignments) == 2

# ── СЦЕНАРИЙ 3: переключение банков (200 раз) ──
for i in range(200):
    win._switch_bank(M.BANKS[i % len(M.BANKS)])
app.processEvents()
win._switch_bank("A")
print("[5] 200 переключений банков — ок")

# виджеты НЕ пересоздавались
assert [id(p) for p in win._pad_slots] == pad_ids_before, "PadWidget пересоздались!"
assert [id(b) for b in win.bank_btns.values()] == bank_ids_before, "Кнопки пересоздались!"
print("[6] виджеты не пересоздавались ✓")

# ── СЦЕНАРИЙ 4: авто-раскладка + очистка ──
for _ in range(20):
    win._auto_assign()
    app.processEvents()
n_auto = len(win.assignments)
win.assignments = {}
win._render_pads()
app.processEvents()
print(f"[7] авто-раскладка ×20 (последняя: {n_auto} пэдов) — ок")

# ── СЦЕНАРИЙ 5: удаление назначенного сэмпла ──
win._auto_assign()
app.processEvents()
target = sids[0]
win.samples.pop(target, None)
win.assignments = {p: v for p, v in win.assignments.items() if v != target}
win._render_pads()
win._render_samples()
win._update_stats()
app.processEvents()
print(f"[8] удаление назначенного сэмпла — ок (осталось {len(win.assignments)})")

# ── СЦЕНАРИЙ 6: drop на все 12 пэдов подряд ──
win._switch_bank("C")
sid = list(win.samples.keys())[0]
for pad in win._pad_slots:
    make_drop(pad, sid)
app.processEvents()
bank_c = [p for p in win.assignments if p[0] == "C"]
print(f"[9] drop на все 12 пэдов банка C: {len(bank_c)}")
assert len(bank_c) == 12

QTimer.singleShot(100, app.quit)
app.exec()

print("\n✅ СТРЕСС-ТЕСТ ПРОЙДЕН — segfault не воспроизводится")
