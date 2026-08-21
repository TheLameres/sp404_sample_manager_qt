#!/usr/bin/env python3
"""
setup.py — сборка standalone macOS-приложения (.app) через py2app.

Использование:
    pip install py2app
    python setup.py py2app            # релизная сборка
    python setup.py py2app -A         # dev-сборка (alias mode, быстрее)

Результат: dist/SP-404SX Manager.app

Примечание: этот файл нужен ТОЛЬКО для сборки .app на macOS.
Обычный запуск — через `poetry run sp404-manager` или `python -m sp404_manager.main`.
"""

import sys
from pathlib import Path
from setuptools import setup

APP = ["run_app.py"]
APP_NAME = "SP-404SX Manager"
VERSION = "1.0.1"

# Иконка (генерируется build_macos.sh → icon.icns)
ICON_FILE = "icon.icns"
DATA_FILES = []

OPTIONS = {
    "argv_emulation": False,        # True ломает Qt event loop — держим False
    "iconfile": ICON_FILE if Path(ICON_FILE).exists() else None,
    "plist": {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "ai.syntx.sp404manager",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "NSHumanReadableCopyright": "© 2026 SYNTX.AI",
        "NSHighResolutionCapable": True,        # Retina
        "LSMinimumSystemVersion": "10.13.0",
        "NSMicrophoneUsageDescription":
            "Приложение может использовать микрофон для записи сэмплов.",
        # Тёмная тема поддерживается
        "NSRequiresAquaSystemAppearance": False,
    },
    # Явно включаем пакеты, которые py2app может не подхватить автоматически
    "packages": [
        "PySide6",
        "shiboken6",
        "sp404_manager",
    ],
    "includes": [
        "sp404_manager.main",
        "sp404_manager.analyzer",
        "sp404_manager.exporter",
        "sp404_manager.platform_utils",
    ],
    # librosa/numpy опциональны — если установлены, включатся
    "excludes": [
        "tkinter",
        "PyQt5",
        "PyQt6",
        "matplotlib",     # librosa тянет, но GUI он не нужен
    ],
    # Только нужные Qt-плагины (уменьшает размер бандла)
    "qt_plugins": [
        "platforms/libqcocoa",
        "audio",
        "multimedia",
        "styles",
    ],
}

# Уберём None-иконку, если файла нет
if OPTIONS["iconfile"] is None:
    del OPTIONS["iconfile"]

setup(
    name=APP_NAME,
    app=APP,
    version=VERSION,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
