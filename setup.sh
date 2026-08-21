#!/bin/bash
# setup.sh — Автоматическая установка SP-404SX Manager на macOS

set -e

echo "╔════════════════════════════════════════════════════════╗"
echo "║  🎛️  SP-404SX Sample Manager — macOS Setup             ║"
echo "╚════════════════════════════════════════════════════════╝"
echo

PLATFORM=$(uname)
if [ "$PLATFORM" != "Darwin" ]; then
    echo "❌ Этот скрипт работает только на macOS"
    exit 1
fi

echo "📦 Проверка зависимостей…"

# Проверяем Homebrew
if ! command -v brew &> /dev/null; then
    echo "⚠️  Homebrew не установлен. Устанавливаю…"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "✓ Homebrew найден"
fi

# Проверяем Python
if ! command -v python3 &> /dev/null; then
    echo "⚠️  Python3 не установлен. Устанавливаю через Homebrew…"
    brew install python@3.11
    PYTHON_PATH=$(brew --prefix python@3.11)/bin/python3
else
    PYTHON_PATH=$(which python3)
    PY_VERSION=$($PYTHON_PATH --version 2>&1 | awk '{print $2}')
    echo "✓ Python $PY_VERSION найден"
fi

# Проверяем Poetry
if ! command -v poetry &> /dev/null; then
    echo "⚠️  Poetry не установлен. Устанавливаю…"
    curl -sSL https://install.python-poetry.org | $PYTHON_PATH -
    export PATH="$HOME/.local/bin:$PATH"
    echo "✓ Poetry установлена"
else
    echo "✓ Poetry найдена"
fi

echo
echo "🔧 Установка зависимостей проекта…"

# Устанавливаем зависимости через Poetry
poetry install --with-extras analysis

echo
echo "🎯 Проверка установки…"

poetry run python -c "
import sys
print(f'✓ Python {sys.version.split()[0]}')

try:
    from PySide6 import QtCore
    print('✓ PySide6 OK')
except ImportError:
    print('✗ PySide6 не найдена')
    sys.exit(1)

try:
    import librosa
    print('✓ librosa OK (анализ включен)')
except ImportError:
    print('⚠️  librosa не найдена (анализ отключен)')

try:
    import numpy
    print('✓ NumPy OK')
except ImportError:
    print('⚠️  NumPy не найдена')
"

echo
echo "✨ Готово!"
echo
echo "🚀 Запуск приложения:"
echo "   poetry run sp404-manager"
echo
echo "📱 Или создай ярлык на рабочем столе:"
echo "   ln -s '$(pwd)' ~/Desktop/SP404-Manager"
echo
