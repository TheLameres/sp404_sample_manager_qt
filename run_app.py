#!/usr/bin/env python3
"""
run_app.py — точка входа для py2app.

py2app требует top-level скрипт, а не модуль пакета.
Этот файл просто вызывает sp404_manager.main.main().

Импорт обёрнут в try/except: в собранном .app у процесса нет видимого
stdout, поэтому сбой импорта (не доехавший в бандл PySide6, битая
зависимость) выглядел для пользователя как молчаливое неоткрытие окна.
Теперь такая ошибка попадает в файл лога.
"""
import sys

try:
    from sp404_manager.main import main
except Exception:
    try:
        from sp404_manager.logging_setup import setup_logging, get_logger
        setup_logging()
        get_logger(__name__).critical(
            "Не удалось импортировать приложение", exc_info=True)
    except Exception:
        import traceback
        traceback.print_exc()
    sys.exit(1)

if __name__ == "__main__":
    main()
