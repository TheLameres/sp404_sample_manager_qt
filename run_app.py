#!/usr/bin/env python3
"""
run_app.py — точка входа для py2app.

py2app требует top-level скрипт, а не модуль пакета.
Этот файл просто вызывает sp404_manager.main.main().
"""
from sp404_manager.main import main

if __name__ == "__main__":
    main()
