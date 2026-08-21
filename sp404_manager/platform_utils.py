#!/usr/bin/env python3
"""
Platform detection and app initialization utilities.
"""
import sys
import platform


def get_platform() -> str:
    """Определяет платформу: 'macos', 'linux', 'windows'."""
    system = platform.system()
    if system == "Darwin":
        return "macos"
    elif system == "Linux":
        return "linux"
    elif system == "Windows":
        return "windows"
    return "unknown"


def get_platform_version() -> str:
    """Возвращает версию ОС."""
    if get_platform() == "macos":
        return platform.mac_ver()[0]
    else:
        return platform.release()


def get_app_dir() -> str:
    """Возвращает путь к директории приложения в зависимости от ОС."""
    from pathlib import Path
    plat = get_platform()
    if plat == "macos":
        # ~/Library/Application Support/SP-404SX Manager/
        return str(Path.home() / "Library" / "Application Support" / "SP-404SX Manager")
    elif plat == "linux":
        # ~/.config/sp404_manager/
        return str(Path.home() / ".config" / "sp404_manager")
    elif plat == "windows":
        # %APPDATA%\SP-404SX Manager\
        import os
        appdata = os.getenv("APPDATA")
        return f"{appdata}\\SP-404SX Manager"
    return str(Path.home() / ".sp404_manager")


def check_dependencies() -> dict:
    """Проверяет доступность зависимостей."""
    result = {
        "pyside6": False,
        "librosa": False,
        "numpy": False,
        "soundfile": False,
    }
    
    try:
        import PySide6
        result["pyside6"] = True
    except ImportError:
        pass
    
    try:
        import librosa
        result["librosa"] = True
    except ImportError:
        pass
    
    try:
        import numpy
        result["numpy"] = True
    except ImportError:
        pass
    
    try:
        import soundfile
        result["soundfile"] = True
    except ImportError:
        pass
    
    return result


def print_system_info():
    """Выводит информацию о системе."""
    plat = get_platform()
    ver = get_platform_version()
    deps = check_dependencies()
    
    print(f"Platform:   {plat} {ver}")
    print(f"Python:     {sys.version.split()[0]}")
    print(f"PySide6:    {'✓' if deps['pyside6'] else '✗'}")
    print(f"librosa:    {'✓' if deps['librosa'] else '⚠'} (анализ)")
    print(f"NumPy:      {'✓' if deps['numpy'] else '✗'}")
    print(f"SoundFile:  {'✓' if deps['soundfile'] else '✗'}")


if __name__ == "__main__":
    print_system_info()
