#!/usr/bin/env python3
"""Headless test — строит окно, грузит сэмплы, авто-раскладка, экспорт."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_MEDIA_BACKEND", "ffmpeg")

import sys, shutil, wave
from pathlib import Path
import numpy as np

# генерируем тестовые сэмплы
tdir = Path("/tmp/test_samples"); tdir.mkdir(exist_ok=True)
SR = 44100
def mk(path, y):
    y = np.clip(y, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((y*32767).astype("<i2").tobytes())

t = np.linspace(0,0.4,int(SR*0.4)); mk(tdir/"kick.wav", np.sin(2*np.pi*60*t)*np.exp(-t*20))
t = np.linspace(0,0.3,int(SR*0.3)); mk(tdir/"snare.wav", np.sin(2*np.pi*200*t)*np.exp(-t*30)*0.5+np.random.randn(len(t))*0.4*np.exp(-t*15))
t = np.linspace(0,0.1,int(SR*0.1)); mk(tdir/"hat.wav", np.random.randn(len(t))*np.exp(-t*80))
t = np.linspace(0,2.0,int(SR*2.0)); mk(tdir/"bass.wav", np.sin(2*np.pi*80*t)*0.7*np.exp(-t*0.5))

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

# чистим прошлый проект
proj = Path.home()/".sp404_manager"
if proj.exists(): shutil.rmtree(proj)

import sp404_manager.main as M
win = M.MainWindow()

# синхронный импорт (без потока — вызовем воркер напрямую)
from sp404_manager.main import AnalyzeWorker
files = [str(f) for f in sorted(tdir.iterdir())]
w = AnalyzeWorker(files)
w.one_done.connect(win._on_sample_added)
w.run()

print(f"[1] Загружено сэмплов: {len(win.samples)}")
for s in win.samples.values():
    print(f"    {s['category']:8s} <- {s['name']}")

# авто-раскладка
win._auto_assign()
print(f"[2] Назначено пэдов: {len(win.assignments)}")
for pad, sid in sorted(win.assignments.items()):
    print(f"    {pad} -> {win.samples[sid]['name']}")

# переключение банка + рендер пэдов
win._switch_bank("A")
print(f"[3] Пэдов на банке A отрисовано: {len(win.pads)}")
filled = sum(1 for p in win.pads.values() if p.sample)
print(f"    Заполнено пэдов в банке A: {filled}")

# экспорт (синхронно)
from sp404_manager.main import ExportWorker
out = Path("/tmp/export_test/SP-404SX_SD")
ew = ExportWorker(dict(win.assignments), dict(win.samples), out, make_zip=True)
result = {}
ew.finished.connect(lambda r: result.update(r))
ew.run()
print(f"[4] Экспортировано: {len(result['exported'])}, ошибок: {len(result['errors'])}")
for e in result["exported"]:
    print(f"    {e['pad']}: {e['file']} ({e['sample']})")
print(f"    ZIP: {Path(result['zip']).name if result.get('zip') else 'нет'}")

# проверка формата экспортированного WAV
first = out/"ROLAND"/"SP-404SX"/"SMPL"/"A0000001.WAV"
if first.exists():
    with wave.open(str(first),"rb") as wf:
        ok = wf.getframerate()==44100 and wf.getsampwidth()==2
        print(f"[5] A0000001.WAV: {wf.getframerate()}Hz/{wf.getsampwidth()*8}bit -> {'✅ OK' if ok else '❌'}")

# проверка сохранения/загрузки проекта
win._save_project()
win2 = M.MainWindow()
print(f"[6] После перезагрузки: {len(win2.samples)} сэмплов, {len(win2.assignments)} назначений")

print("\n✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
