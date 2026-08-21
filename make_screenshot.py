#!/usr/bin/env python3
"""Рендер скриншота UI через offscreen platform (для превью)."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_MEDIA_BACKEND"] = "ffmpeg"
import sys, shutil, wave
from pathlib import Path
import numpy as np

# тестовые сэмплы
tdir = Path("/tmp/shot_samples"); tdir.mkdir(exist_ok=True)
SR=44100
def mk(p,y):
    y=np.clip(y,-1,1)
    with wave.open(str(p),"wb") as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(SR)
        w.writeframes((y*32767).astype("<i2").tobytes())
names = {
    "808_kick.wav": lambda t: np.sin(2*np.pi*55*t)*np.exp(-t*15),
    "trap_snare.wav": lambda t: np.sin(2*np.pi*210*t)*np.exp(-t*30)*0.5+np.random.randn(len(t))*0.4*np.exp(-t*14),
    "closed_hat.wav": lambda t: np.random.randn(len(t))*np.exp(-t*80),
    "open_hat.wav": lambda t: np.random.randn(len(t))*np.exp(-t*20),
    "sub_bass.wav": lambda t: np.sin(2*np.pi*70*t)*0.8*np.exp(-t*0.4),
    "rhodes_chord.wav": lambda t: (np.sin(2*np.pi*440*t)+np.sin(2*np.pi*554*t)*.7+np.sin(2*np.pi*659*t)*.5)*np.exp(-t*0.3),
    "vinyl_fx.wav": lambda t: np.random.randn(len(t))*0.2,
    "clap.wav": lambda t: np.random.randn(len(t))*np.exp(-t*40),
}
durs = {"sub_bass.wav":2.0,"rhodes_chord.wav":3.0,"vinyl_fx.wav":4.0}
for nm,fn in names.items():
    d = durs.get(nm,0.4)
    t = np.linspace(0,d,int(SR*d))
    mk(tdir/nm, fn(t))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication(sys.argv)

proj = Path.home()/".sp404_manager"
if proj.exists(): shutil.rmtree(proj)

import sp404_manager.main as M
win = M.MainWindow()
win.resize(1180, 780)

from sp404_manager.main import AnalyzeWorker
files=[str(f) for f in sorted(tdir.iterdir())]
w=AnalyzeWorker(files); w.one_done.connect(win._on_sample_added); w.run()
win._auto_assign()
win._switch_bank("A")
win._render_samples()
win.show()

# даём Qt отрисоваться, затем grab
def shoot():
    pix = win.grab()
    pix.save("/home/user/sp404_qt/screenshot.png")
    print("saved", pix.width(), "x", pix.height())
    app.quit()
QTimer.singleShot(600, shoot)
app.exec()
