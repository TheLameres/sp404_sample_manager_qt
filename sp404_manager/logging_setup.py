#!/usr/bin/env python3
"""
logging_setup.py — Единая точка конфигурации логирования приложения.

Модуль намеренно не зависит ни от чего, кроме stdlib и platform_utils:
он подключается самым первым в main() и должен работать даже если
PySide6/librosa не установлены (или сломаны).

Использование:

    # один раз, в точке входа
    from .logging_setup import setup_logging, log_system_info
    setup_logging()
    log_system_info()

    # в любом модуле
    from .logging_setup import get_logger
    log = get_logger(__name__)
    log.info("Импортирую %d файлов", n)

Куда пишутся логи:
    macOS:   ~/Library/Application Support/SP-404SX Manager/logs/
    Linux:   ~/.config/sp404_manager/logs/
    Windows: %APPDATA%\\SP-404SX Manager\\logs\\

Переменные окружения:
    SP404_LOG_LEVEL — уровень консоли (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    SP404_LOG_DIR   — переопределить каталог логов
"""

import logging
import logging.handlers
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path

# ─────────────────────────────────────────────────────────────
#  Константы
# ─────────────────────────────────────────────────────────────
LOGGER_NAME = "sp404_manager"
LOG_FILENAME = "sp404_manager.log"

MAX_BYTES = 2 * 1024 * 1024          # 2 МБ на файл
BACKUP_COUNT = 5                      # + 5 архивов → максимум ~12 МБ

DEFAULT_CONSOLE_LEVEL = logging.INFO
FILE_LEVEL = logging.DEBUG            # в файл пишем всегда максимально подробно

FILE_FORMAT = (
    "%(asctime)s %(levelname)-8s [%(threadName)s] "
    "%(name)s:%(lineno)d — %(message)s"
)
CONSOLE_FORMAT = "%(levelname)-8s %(name)s — %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Шумные сторонние логгеры: на DEBUG они забивают файл тысячами строк
# (numba компилирует ядра librosa при каждом анализе).
NOISY_LOGGERS = (
    "numba", "librosa", "soundfile", "matplotlib", "PIL", "urllib3", "asyncio",
)

# ─────────────────────────────────────────────────────────────
#  Внутреннее состояние (setup_logging идемпотентен)
# ─────────────────────────────────────────────────────────────
_configured = False
_log_file: "Path | None" = None
_log_dir: "Path | None" = None


# ─────────────────────────────────────────────────────────────
#  Пути
# ─────────────────────────────────────────────────────────────
def get_log_dir() -> Path:
    """Каталог логов. SP404_LOG_DIR имеет приоритет над путём ОС."""
    env_dir = os.getenv("SP404_LOG_DIR")
    if env_dir:
        return Path(env_dir).expanduser()
    # локальный импорт: не тянем platform_utils при простом импорте модуля
    from .platform_utils import get_app_dir
    return Path(get_app_dir()) / "logs"


def get_log_file() -> "Path | None":
    """Путь к активному файлу лога (None, если файловый хендлер не поднялся)."""
    return _log_file


def _resolve_level(level) -> int:
    """int | 'DEBUG' | None → int. None → SP404_LOG_LEVEL → INFO."""
    if level is None:
        level = os.getenv("SP404_LOG_LEVEL")
    if level is None:
        return DEFAULT_CONSOLE_LEVEL
    if isinstance(level, int):
        return level
    resolved = logging.getLevelName(str(level).strip().upper())
    return resolved if isinstance(resolved, int) else DEFAULT_CONSOLE_LEVEL


# ─────────────────────────────────────────────────────────────
#  Хендлеры
# ─────────────────────────────────────────────────────────────
def _make_file_handler(log_dir: Path):
    """RotatingFileHandler в utf-8. Возвращает (handler, log_path) или (None, None).

    utf-8 обязателен: в сообщениях есть кириллица и эмодзи, а на Windows
    хендлер по умолчанию берёт cp1251 и падает на первом же '✅'.
    """
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / LOG_FILENAME
        handler = logging.handlers.RotatingFileHandler(
            str(path),
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
            delay=False,
        )
        handler.setLevel(FILE_LEVEL)
        handler.setFormatter(logging.Formatter(FILE_FORMAT, datefmt=DATE_FORMAT))
        return handler, path
    except OSError as exc:
        # Каталог недоступен (read-only том, sandbox, нет прав) — не падаем,
        # приложение обязано стартовать даже без файлового лога.
        print(f"[logging] не удалось открыть файл лога в {log_dir}: {exc}",
              file=sys.stderr)
        return None, None


def _make_console_handler(level: int):
    """Консольный хендлер. errors='replace' — чтобы эмодзи не роняли вывод."""
    stream = sys.stderr
    try:
        # Python 3.7+: подменяем политику ошибок кодирования на месте.
        stream.reconfigure(errors="replace")
    except (AttributeError, ValueError, OSError):
        pass
    handler = logging.StreamHandler(stream)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(CONSOLE_FORMAT, datefmt=DATE_FORMAT))
    return handler


# ─────────────────────────────────────────────────────────────
#  Публичный API
# ─────────────────────────────────────────────────────────────
def setup_logging(level=None, log_dir=None, console: bool = True,
                  force: bool = False) -> "Path | None":
    """Настраивает логирование процесса. Вызывать один раз, в main().

    level    — уровень КОНСОЛИ (в файл всегда DEBUG). None → SP404_LOG_LEVEL → INFO.
    log_dir  — каталог логов. None → get_log_dir().
    console  — писать ли в stderr (в собранном .app смысла нет).
    force    — пересоздать хендлеры, даже если setup уже вызывался.

    Возвращает путь к файлу лога либо None, если файл открыть не удалось.

    Идемпотентно: повторный вызов без force ничего не делает — иначе тесты
    и повторный запуск main() дублировали бы каждую строку.
    """
    global _configured, _log_file, _log_dir

    if _configured and not force:
        return _log_file

    console_level = _resolve_level(level)
    target_dir = Path(log_dir).expanduser() if log_dir else get_log_dir()

    root = logging.getLogger()
    if force:
        for old in root.handlers[:]:
            root.removeHandler(old)
            try:
                old.close()
            except Exception:
                pass

    # Хендлеры вешаем на root: так в лог попадают и наши модули, и полезные
    # предупреждения библиотек. Уровень root — минимальный из двух, реальную
    # фильтрацию делают сами хендлеры.
    root.setLevel(min(FILE_LEVEL, console_level))

    file_handler, path = _make_file_handler(target_dir)
    if file_handler is not None:
        root.addHandler(file_handler)

    if console:
        root.addHandler(_make_console_handler(console_level))

    # Глушим шумные библиотеки, иначе DEBUG-файл нечитаем.
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # warnings.warn(...) → лог, а не тихий stderr.
    logging.captureWarnings(True)

    _log_file = path
    _log_dir = target_dir
    _configured = True

    get_logger(__name__).debug(
        "Логирование настроено: файл=%s, уровень консоли=%s",
        path, logging.getLevelName(console_level),
    )
    return path


def get_logger(name: str = None) -> logging.Logger:
    """Логгер модуля. Идиома: log = get_logger(__name__).

    Имена вида 'sp404_manager.analyzer' сохраняются как есть; посторонние
    имена подвешиваются под 'sp404_manager', чтобы иерархия была единой.
    """
    if not name or name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    if name.startswith(LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def log_system_info(logger: logging.Logger = None) -> None:
    """Пишет «паспорт» среды. Вызывать сразу после setup_logging().

    Снимает большую часть вопросов при разборе баг-репорта: версия, ОС,
    Python и наличие опциональных зависимостей видны в первых строках лога.
    """
    log = logger or get_logger(__name__)
    try:
        from . import __version__
    except Exception:
        __version__ = "unknown"

    try:
        from .platform_utils import (get_platform, get_platform_version,
                                     check_dependencies)
        plat = f"{get_platform()} {get_platform_version()}"
        deps = check_dependencies()
    except Exception:
        log.exception("Не удалось собрать информацию о системе")
        return

    log.info("─" * 60)
    log.info("SP-404SX Sample Manager v%s", __version__)
    log.info("Платформа:    %s", plat)
    log.info("Python:       %s", sys.version.split()[0])
    log.info("Исполняемый:  %s", sys.executable)
    log.info("Frozen:       %s", getattr(sys, "frozen", False))
    log.info("Зависимости:  %s",
             ", ".join(f"{k}={'да' if v else 'НЕТ'}" for k, v in deps.items()))
    log.info("Файл лога:    %s", _log_file)
    log.info("─" * 60)


@contextmanager
def log_duration(logger: logging.Logger, operation: str, level: int = logging.DEBUG,
                 **context):
    """Замеряет длительность операции.

        with log_duration(log, "анализ", file=path.name):
            info = analyze_sample(path)

    Успех → одна строка с временем на указанном уровне.
    Исключение → ERROR с traceback и временем до падения, исключение
    пробрасывается дальше (контекст ничего не проглатывает).
    """
    extra = " ".join(f"{k}={v}" for k, v in context.items())
    suffix = f" ({extra})" if extra else ""
    start = time.perf_counter()
    try:
        yield
    except Exception:
        elapsed = (time.perf_counter() - start) * 1000
        logger.error("%s — ОШИБКА через %.0f мс%s", operation, elapsed, suffix,
                     exc_info=True)
        raise
    else:
        elapsed = (time.perf_counter() - start) * 1000
        logger.log(level, "%s — готово за %.0f мс%s", operation, elapsed, suffix)


def shutdown_logging() -> None:
    """Сбрасывает буферы и закрывает хендлеры (вызывать при выходе)."""
    global _configured
    logging.shutdown()
    _configured = False
