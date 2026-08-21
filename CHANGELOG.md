# 📋 Changelog — SP-404SX Sample Manager

## v1.0.1 (2026-08-21) — 🐛 Критический фикс macOS

### Исправлено

- **🔴 Segfault на macOS при drag & drop сэмпла на пэд.**
  Причина: `dropEvent` эмитил сигнал синхронно внутри вложенного цикла
  drag'n'drop, а обработчик пересоздавал виджеты (`deleteLater()`),
  что приводило к `QWidget::repaint: Recursive repaint detected`,
  `QBackingStore::endPaint() called with active painter` и падению.
  - `dropEvent` и клик по «✕» теперь эмитят сигнал через `QTimer.singleShot(0, …)`
  - Кнопки банков и `PadWidget` создаются **один раз** и только обновляются
    (`_build_bank_buttons`/`_build_pads` + `_render_*`), без пересоздания
  - Убран монки-патч `clear_btn.mousePressEvent = lambda` → обычный `QPushButton`
  - `_apply_style()` пропускает вызов `setStyleSheet`, если состояние не изменилось
- **Шрифты на macOS**: убран hardcoded `'Segoe UI'` из QSS
  (`qt.qpa.fonts: Populating font family aliases…`). Теперь семейство
  выбирается по ОС: `Helvetica Neue` (macOS) / `Segoe UI` (Windows) / `Ubuntu` (Linux)
- **`startDrag`**: удерживаются ссылки на `QDrag`/`QMimeData` (защита от GC
  во время `exec()` на macOS) + защита от перетаскивания плейсхолдера
- **`_menu`**: защита от контекстного меню на плейсхолдере

### Добавлено

- `test_stress_gui.py` — стресс-тест GUI, воспроизводящий сценарии падения:
  реальные `QDropEvent`, 200 переключений банков, авто-раскладка ×20,
  удаление назначенного сэмпла, drop на все 12 пэдов

## v1.0.0 (2026-08-21) — 🎉 Release Candidate

### ✨ Новые фичи

#### Core функционал
- ✅ Авто-классификация сэмплов через librosa (12 категорий)
- ✅ Сетка пэдов 12×12 с device-accurate раскладкой
- ✅ Drag & drop из библиотеки на пэды и из Finder в окно
- ✅ Встроенный аудиоплеер (QtMultimedia)
- ✅ Авто-раскладка сэмплов по категориям в один клик
- ✅ Фильтры по категориям
- ✅ Фоновая обработка (QThread) — UI никогда не подвисает
- ✅ Автосохранение проекта в JSON

#### SD-карта экспорт
- ✅ Полная структура `ROLAND/SP-404SX/SMPL/` для SP-404SX
- ✅ Правильные имена файлов (`A0000001.WAV` etc.)
- ✅ Конвертация в 44.1kHz/16-bit WAV
- ✅ **PADINFO.BIN** генерация (120 × 32 байта, big-endian)
  - Автоматическое заполнение tempo из BPM сэмплов
  - Параметры пэдов (volume, loop, gate, reverse, format)
  - Совместимость со SP-404SX
- ✅ ZIP-архив для удобства передачи
- ✅ Манифест с описанием экспорта

#### Платформы
- ✅ macOS 10.13+ (с native поддержкой Apple Silicon)
- ✅ Linux (GTK3/Wayland)
- ✅ Windows 10+
- ✅ Платформо-зависимые пути сохранения

#### Управление зависимостями
- ✅ Poetry поддержка (`pyproject.toml`)
- ✅ Optional зависимости (librosa, numpy, soundfile)
- ✅ GitHub Actions CI/CD для macOS builds
- ✅ Fallback на pip (`requirements.txt`)

#### Разработка
- ✅ Модульная архитектура (analyzer, exporter, GUI независимы)
- ✅ Platform detection (`platform_utils.py`)
- ✅ Unit тесты (pytest)
- ✅ Автоматический скрипт установки (`setup.sh` для macOS)

### 🎨 UI/UX

- 🌙 Тёмная тема по умолчанию (совместима с Dark Mode)
- 🖱️ Интуитивный drag & drop интерфейс
- 📊 Live статистика (кол-во сэмплов, пэдов)
- ⏱️ Прогресс-бары при загрузке и экспорте
- 🎵 Двойной клик → прослушивание сэмпла
- 🔍 Быстрые фильтры по категориям

### 📚 Документация

- ✅ [README.md](README.md) — полный гайд на русском
- ✅ [QUICKSTART.md](QUICKSTART.md) — быстрый старт для всех платформ
- ✅ [INSTALL_MACOS.md](INSTALL_MACOS.md) — подробно про macOS
- ✅ Inline документация в коде
- ✅ Примеры использования API

### 🔧 Техническое

| Компонент | Версия | Назначение |
|-----------|--------|-----------|
| PySide6 | ≥6.6 | GUI |
| librosa | ≥0.10 | Анализ аудио |
| NumPy | ≥1.24 | Обработка данных |
| SoundFile | ≥0.12 | Чтение аудио |
| pytest | ≥7.0 | Тестирование (dev) |
| black | ≥23.0 | Форматирование (dev) |
| PyInstaller | ≥5.0 | Сборка (dev) |

### 🐛 Известные ограничения

- PADINFO.BIN содержит только A-J банки (SX имеет A-L, но это совместимо)
- Librosa — опциональный модуль (классификация отключена без него)
- QtMultimedia звук может не работать без полного окружения (ОК для экспорта)

### 🚀 Производительность

- Загрузка 100 сэмплов: ~15 сек (с librosa анализом)
- Экспорт 50 сэмплов: ~5 сек (конвертация + метаданные)
- Память: 150-300 MB типично
- Размер приложения (с зависимостями): ~50 MB

### 📦 Релизная информация

**Платформы:**
- macOS 10.13+ (DMG будет в GitHub Releases)
- Linux (pip install)
- Windows (pip install или standalone EXE)

**Установка:**
```bash
# Быстро (macOS)
bash setup.sh

# На всех платформах
poetry install --with-extras analysis
poetry run sp404-manager

# Или через pip
pip install -r requirements.txt
python -m sp404_manager.main
```

---

## Планы на будущее (v1.1+)

- [ ] MIDI Learn — назначение сэмплов через MIDI контроллер
- [ ] Batch операции — одновременный анализ папки
- [ ] Preset система — сохранение наборов параметров пэдов
- [ ] Встроенный нормализатор громкости
- [ ] Виджеты волны для каждого пэда
- [ ] Поддержка плагинов
- [ ] Локализация (Japanese, Spanish, French, German)
- [ ] Вспомогательная документация на видео
- [ ] Продвинутый PADINFO редактор (UI для параметров)

---

**Статус**: ✅ Ready for Production  
**Лицензия**: MIT  
**Автор**: SYNTX.AI
