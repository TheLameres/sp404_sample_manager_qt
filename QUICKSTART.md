# 🚀 Быстрый старт — SP-404SX Manager

## На macOS (рекомендуется)

### 1️⃣ Автоматическая установка (5 минут)
```bash
cd sp404_qt
bash setup.sh
poetry run sp404-manager
```

### 2️⃣ Ручная установка (если setup.sh не сработал)
```bash
# Установи Poetry
curl -sSL https://install.python-poetry.org | python3 -

# Перейди в папку проекта
cd sp404_qt

# Установи зависимости
poetry install --with-extras analysis

# Запусти
poetry run sp404-manager
```

## На Linux

```bash
# Установи Poetry
curl -sSL https://install.python-poetry.org | python3 -

cd sp404_qt
poetry install --with-extras analysis
poetry run sp404-manager
```

## На Windows

```bash
# Установи Python 3.11+ с python.org
# Установи Poetry
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

cd sp404_qt
poetry install --with-extras analysis
poetry run sp404-manager
```

## Если Poetry не работает

Установи напрямую через pip:
```bash
pip install -r requirements.txt
python -m sp404_manager.main
```

## ⚠️ Решение проблем

### "PySide6 not found"
```bash
poetry install --no-cache
```

### "librosa не работает"
```bash
# На macOS
brew install python@3.11
poetry env use $(which python3.11)
poetry install

# На Linux
sudo apt install python3.11-dev
poetry install
```

### "Нет звука в плеере" (macOS)
Это нормально без полного окружения. Основной функционал (drag&drop, экспорт) работает.

---

**Готово!** 🎉 Теперь:
1. Перетащи сэмплы в окно приложения
2. Нажми ✨ «Авто-раскладка»
3. Нажми 💾 «Экспорт SD» и выбери папку
4. Скинь ZIP на SD-карту в SP-404SX

Подробнее в [README.md](README.md) и [INSTALL_MACOS.md](INSTALL_MACOS.md)
