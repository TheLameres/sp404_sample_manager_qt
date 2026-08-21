# 🎛️ SP-404SX Sample Manager — macOS

Нативное десктопное приложение для управления сэмплами Roland SP-404SX на macOS.

**Без Flask, без браузера, без JS** — чистый Qt (PySide6) + Poetry для управления зависимостями.

[README на русском](README.md) | [English README](README.en.md)

## 🍎 Требования macOS

- **macOS 10.13+** (High Sierra или новее)
- **Python 3.9+** (рекомендуется 3.11+)
- **Homebrew** (для установки зависимостей)

## 📦 Установка на macOS

### Вариант 1: с помощью Poetry (рекомендуется)

```bash
# 1. Установи Poetry (если ещё не установлено)
curl -sSL https://install.python-poetry.org | python3 -

# 2. Клонируй или распакуй проект
unzip sp404_qt.zip
cd sp404_qt

# 3. Установи зависимости
poetry install --with-extras analysis

# 4. Запусти приложение
poetry run sp404-manager
# или
poetry run python -m sp404_manager.main
```

### Вариант 2: с помощью pip (простой способ)

```bash
# 1. Создай virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Установи зависимости
pip install -r requirements.txt
# или только основное (без анализа)
pip install PySide6

# 3. Запусти приложение
python sp404_manager/main.py
```

### Вариант 3: Standalone App (macOS DMG)

Скоро будет доступен предскомпилированный `.app` пакет.
Скачай, перетащи в `/Applications`, и готово!

## 🔧 Решение проблем на macOS

### PySide6 не найдена
```bash
poetry install --no-cache
# или
pip install --upgrade PySide6
```

### Librosa/NumPy ошибки при импорте
```bash
# Установи через Homebrew
brew install python@3.11
poetry env use $(which python3.11)
poetry install --with-extras analysis
```

### «Приложение повреждено» при запуске
Это нормально для неподписанного приложения. Разреши в Параметры → Безопасность:
```bash
xattr -d com.apple.quarantine "$(which sp404-manager)"
```

### Нет звука в плеере
Убедись, что системные библиотеки PySide6 на месте:
```bash
poetry run python -c "from PySide6 import QtMultimedia; print('OK')"
```

## 🚀 Быстрый старт

1. **Добавь сэмплы** — перетащи WAV/MP3/AIFF файлы в окно
2. **Авто-анализ** — librosa классифицирует их (kick/snare/bass/loops…)
3. **Разложи по пэдам** — вручную или кнопкой ✨ «Авто-раскладка»
4. **Экспортируй SD** — нажми 💾 «Экспорт SD» → выбери папку → ZIP готов

SD-карта структурируется автоматически в `ROLAND/SP-404SX/SMPL/` с метаданными `PADINFO.BIN`.

## 📁 Структура проекта

```
sp404_qt/
├── pyproject.toml                 # Poetry конфиг
├── poetry.lock                    # Lock-файл зависимостей
├── requirements.txt               # Fallback для pip
├── README.md                      # Документация (русский)
├── INSTALL_MACOS.md              # Этот файл
├── sp404_manager/
│   ├── __init__.py
│   ├── main.py                    # GUI (PySide6)
│   ├── analyzer.py                # librosa анализ
│   └── exporter.py                # SD-карта экспорт + PADINFO.BIN
├── tests/
│   └── test_*.py                  # Unit тесты
└── screenshots/
    └── macos_screenshot.png
```

## 💻 Запуск в режиме разработки

```bash
# Установи с dev-зависимостями
poetry install --with dev

# Форматирование кода (Black)
poetry run black sp404_manager/

# Линтинг (Flake8)
poetry run flake8 sp404_manager/

# Тесты
poetry run pytest tests/

# Запуск app с дебагом
poetry run python -m sp404_manager.main
```

## 🛠️ Сборка standalone приложения (PyInstaller)

```bash
# Установи PyInstaller
poetry add --group dev pyinstaller

# Собери
poetry run pyinstaller --onefile \
  --windowed \
  --name "SP-404SX Manager" \
  --icon icon.icns \
  sp404_manager/main.py

# Результат в ./dist/
```

## 📦 Публикация через pip

```bash
# Сборка дистрибутива
poetry build

# Загрузка на PyPI
poetry publish

# Тогда пользователи смогут установить
pip install sp404-manager
```

## ⚙️ macOS-специфичные фичи

### Интеграция с Finder
При запуске из Finder (двойной клик на `.app`) приложение:
- Автоматически открывает Finder при экспорте
- Поддерживает drag & drop из Finder прямо в окно

### Dark Mode
Приложение полностью поддерживает Dark Mode в macOS.
Тема автоматически следит за системными настройками.

### Universal Binary (Apple Silicon)
PySide6 имеет native поддержку Apple Silicon (M1/M2/M3).
Ничего делать не нужно — просто устанавливай через Poetry.

## 🐛 Reporting Issues

Если у тебя проблема:
1. Проверь логи: `python -m sp404_manager.main 2>&1 | head -50`
2. Убедись Python >= 3.9: `python --version`
3. Обнови зависимости: `poetry update`
4. Попробуй переустановку: `poetry install --no-cache`

## 📞 Поддержка

- Официальный сайт: https://syntx.ai
- Issues: Открой issue в репозитории
- Обсуждение: Дискорд/Telegram (скоро)

---

**SP-404SX Manager © 2024 by SYNTX.AI** — MIT License
