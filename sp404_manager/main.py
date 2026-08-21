#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║   SP-404SX Sample Manager — Desktop (PySide6)               ║
║   • Авто-классификация сэмплов (librosa)                    ║
║   • Назначение на пэды через drag & drop                    ║
║   • Экспорт в формат SD-карты SP-404SX                       ║
║                                            by SYNTX.AI       ║
╚══════════════════════════════════════════════════════════════╝
"""

import logging
import sys
import json
import threading
import uuid
import shutil
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import (Qt, QThread, Signal, QObject, QUrl, QSize,
                            QMimeData, QByteArray, QTimer, QtMsgType,
                            qInstallMessageHandler)
from PySide6.QtGui import QFont, QColor, QPalette, QIcon, QDrag, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QFileDialog, QComboBox,
    QFrame, QScrollArea, QSizePolicy, QProgressBar, QMessageBox, QMenu,
    QStatusBar, QAbstractItemView
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from .analyzer import (analyze_sample, CATEGORY_META, CATEGORY_ORDER,
                       SUPPORTED_EXT, HAVE_LIBROSA)
from .exporter import export_sd, auto_assign, pad_to_filename
from .platform_utils import get_app_dir, get_platform
from .logging_setup import (setup_logging, get_logger, log_system_info,
                            get_log_file, shutdown_logging)

log = get_logger(__name__)
_qt_log = get_logger("sp404_manager.qt")


# ─────────────────────────────────────────────────────────────────────
#  Конфигурация
# ─────────────────────────────────────────────────────────────────────
BANKS = list("ABCDEFGHIJKL")           # 12 банков
PADS_PER_BANK = 12
APP_DIR = Path(get_app_dir())
SAMPLES_DIR = APP_DIR / "samples"
PROJECT_FILE = APP_DIR / "project.json"

MIME_SAMPLE = "application/x-sp404-sample-id"


def ensure_app_dirs() -> bool:
    """Создаёт рабочие каталоги приложения.

    Раньше mkdir() выполнялся на уровне модуля, то есть при импорте —
    до того, как логирование настроено. Сбой (read-only том, нет прав,
    отсутствующий %APPDATA%) приводил к падению на импорте вообще без
    диагностики. Теперь это явный вызов из main() и MainWindow.__init__.
    """
    ok = True
    for d in (APP_DIR, SAMPLES_DIR):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            log.exception("Не удалось создать рабочий каталог %s", d)
            ok = False
    if ok:
        log.debug("Рабочие каталоги готовы: %s", APP_DIR)
    return ok


# ─────────────────────────────────────────────
#  Стиль (тёмная тема)
# ─────────────────────────────────────────────
STYLESHEET = """
QMainWindow, QWidget { background:#0d0d10; color:#e8e8ee;
    font-size:13px; }
QLabel#title { font-size:18px; font-weight:700; }
QLabel#tag   { color:#8a8a99; font-size:11px; }
QLabel#h2    { color:#8a8a99; font-size:12px; font-weight:700;
    text-transform:uppercase; letter-spacing:1px; }

QPushButton { background:#1e1e26; border:1px solid #2a2a34; border-radius:8px;
    padding:7px 13px; color:#e8e8ee; font-weight:600; }
QPushButton:hover { background:#2d2d3a; border-color:#3a86ff; }
QPushButton:pressed { background:#3a86ff; }
QPushButton#primary { background:#ff5c38; border-color:#ff5c38; color:#fff; }
QPushButton#primary:hover { background:#ff714f; }
QPushButton#ok { background:#06d6a0; border-color:#06d6a0; color:#04231a; }
QPushButton#ok:hover { background:#0aebb0; }

QComboBox { background:#1e1e26; border:1px solid #2a2a34; border-radius:8px;
    padding:6px 10px; color:#e8e8ee; }
QComboBox::drop-down { border:none; }
QComboBox QAbstractItemView { background:#1e1e26; color:#e8e8ee;
    selection-background-color:#3a86ff; border:1px solid #2a2a34; }

QListWidget { background:#16161c; border:1px solid #2a2a34; border-radius:10px;
    padding:5px; outline:none; }
QListWidget::item { background:#1e1e26; border:1px solid #2a2a34;
    border-radius:8px; padding:8px; margin:3px; }
QListWidget::item:hover { border-color:#3a86ff; background:#2d2d3a; }
QListWidget::item:selected { border-color:#ff5c38; background:#2a2018; }

QScrollBar:vertical { background:#0d0d10; width:10px; margin:0; }
QScrollBar::handle:vertical { background:#2a2a34; border-radius:5px; min-height:24px; }
QScrollBar::add-line, QScrollBar::sub-line { height:0; }

QProgressBar { background:#1e1e26; border:1px solid #2a2a34; border-radius:6px;
    text-align:center; color:#e8e8ee; height:18px; }
QProgressBar::chunk { background:#3a86ff; border-radius:5px; }

QFrame#card { background:#16161c; border:1px solid #2a2a34; border-radius:14px; }
QStatusBar { background:#16161c; color:#8a8a99; }
QMenu { background:#1e1e26; color:#e8e8ee; border:1px solid #2a2a34; }
QMenu::item:selected { background:#3a86ff; }
"""


# ─────────────────────────────────────────────
#  Фоновый воркер: анализ загруженных файлов
# ─────────────────────────────────────────────
class AnalyzeWorker(QObject):
    progress = Signal(int, int)          # done, total
    one_done = Signal(dict)              # готовый sample dict
    finished = Signal(int)              # сколько добавлено
    failed = Signal(str)                 # непредвиденный сбой воркера

    def __init__(self, filepaths):
        super().__init__()
        self.filepaths = filepaths

    def run(self):
        total = len(self.filepaths)
        added = 0
        log.info("Импорт: анализирую %d файл(ов)", total)
        try:
            for i, src in enumerate(self.filepaths):
                src = Path(src)
                if src.suffix.lower() not in SUPPORTED_EXT:
                    log.debug("Пропущен неподдерживаемый файл: %s", src.name)
                    self.progress.emit(i + 1, total)
                    continue
                # копируем в хранилище приложения
                dest = SAMPLES_DIR / src.name
                j = 1
                while dest.exists():
                    dest = SAMPLES_DIR / f"{src.stem}_{j}{src.suffix}"
                    j += 1
                try:
                    shutil.copy2(str(src), str(dest))
                except Exception:
                    # Раньше файл просто "не появлялся" в списке без
                    # единого объяснения — почти неотличимо от того, что
                    # librosa не смогла его классифицировать.
                    log.warning("Не удалось скопировать %s в хранилище",
                                src, exc_info=True)
                    self.progress.emit(i + 1, total)
                    continue

                info = analyze_sample(dest)
                sample = {
                    "id":       f"s_{uuid.uuid4().hex[:8]}",
                    "name":     dest.name,
                    "path":     str(dest),
                    "category": info["category"],
                    "duration": info.get("duration", 0),
                    "tempo":    info.get("tempo", 0),
                    "analyzed": info.get("analyzed", False),
                }
                self.one_done.emit(sample)
                added += 1
                self.progress.emit(i + 1, total)
        except Exception as e:
            # Без этого except необработанное исключение убивало QThread
            # молча: finished никогда не эмитился, прогресс-бар в GUI
            # оставался висеть навечно (см. шаг 2, threading.excepthook
            # не покрывает QThread во всех сборках PySide6). Эмитим
            # только failed (как и ExportWorker) — иначе оба обработчика
            # сработают на один и тот же сбой и сообщение об ошибке в
            # статус-баре тут же перезатрётся сообщением об успехе.
            log.exception("AnalyzeWorker: сбой после %d/%d файлов", added, total)
            self.failed.emit(str(e))
            return
        log.info("Импорт завершён: добавлено %d из %d", added, total)
        self.finished.emit(added)


# ─────────────────────────────────────────────
#  Фоновый воркер: экспорт SD-карты
# ─────────────────────────────────────────────
class ExportWorker(QObject):
    progress = Signal(int, int)
    finished = Signal(dict)
    failed = Signal(str)                 # непредвиденный сбой воркера

    def __init__(self, assignments, samples, out_dir, make_zip=True):
        super().__init__()
        self.assignments = assignments
        self.samples = samples
        self.out_dir = Path(out_dir)
        self.make_zip = make_zip

    def run(self):
        try:
            result = export_sd(self.assignments, self.samples, self.out_dir,
                               progress_cb=lambda d, t: self.progress.emit(d, t))
            # манифест
            manifest = {
                "project": "SP-404SX export",
                "exported_at": datetime.now().isoformat(),
                "pads": result["exported"],
                "errors": result["errors"],
            }
            with open(self.out_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            result["zip"] = None
            if self.make_zip:
                zip_base = str(self.out_dir.parent / (self.out_dir.name + "_SP404SX"))
                zip_path = shutil.make_archive(zip_base, "zip", str(self.out_dir))
                result["zip"] = zip_path
        except Exception as e:
            # Как и в AnalyzeWorker: без этого except сбой (например,
            # переполнен диск при записи ZIP, нет прав на out_dir) убивал
            # поток без единого сигнала — GUI навечно оставался с
            # прогресс-баром экспорта и без диагностики.
            log.exception("ExportWorker: непредвиденный сбой экспорта")
            self.failed.emit(str(e))
            return
        self.finished.emit(result)


# ─────────────────────────────────────────────
#  Виджет одного пэда (drag & drop target)
# ─────────────────────────────────────────────
class PadWidget(QFrame):
    clicked   = Signal(str)               # pad_id
    assigned  = Signal(str, str)          # pad_id, sample_id (drop)
    cleared   = Signal(str)               # pad_id

    def __init__(self, pad_id: str):
        super().__init__()
        self.pad_id = pad_id
        self.sample = None
        self.setAcceptDrops(True)
        self.setFixedSize(150, 130)
        self.setCursor(Qt.PointingHandCursor)
        self._build()
        self._apply_style(False, False)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)

        top = QHBoxLayout()
        self.num_lbl = QLabel(self.pad_id[1:])
        self.num_lbl.setStyleSheet("color:#8a8a99;font-weight:700;font-size:11px;")
        top.addWidget(self.num_lbl)
        top.addStretch()
        self.clear_btn = QPushButton("✕")
        self.clear_btn.setFixedSize(18, 18)
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setFlat(True)
        self.clear_btn.setStyleSheet(
            "QPushButton{color:#8a8a99;border:none;background:transparent;"
            "font-size:12px;padding:0;}QPushButton:hover{color:#ff5c38;}")
        self.clear_btn.hide()
        self.clear_btn.clicked.connect(self._on_clear)
        top.addWidget(self.clear_btn)
        lay.addLayout(top)

        self.icon_lbl = QLabel("")
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        self.icon_lbl.setStyleSheet("font-size:26px;")
        lay.addWidget(self.icon_lbl)

        self.name_lbl = QLabel("— пусто —")
        self.name_lbl.setAlignment(Qt.AlignCenter)
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setStyleSheet("color:#8a8a99;font-size:10px;")
        lay.addWidget(self.name_lbl)

        self.cat_lbl = QLabel("")
        self.cat_lbl.setAlignment(Qt.AlignCenter)
        self.cat_lbl.setStyleSheet("color:#8a8a99;font-size:9px;")
        lay.addWidget(self.cat_lbl)

    def set_sample(self, sample):
        self.sample = sample
        if sample:
            meta = CATEGORY_META.get(sample["category"], CATEGORY_META["unknown"])
            self.icon_lbl.setText(meta["icon"])
            name = sample["name"]
            self.name_lbl.setText(name if len(name) <= 22 else name[:20] + "…")
            self.name_lbl.setStyleSheet("color:#e8e8ee;font-size:10px;")
            self.cat_lbl.setText(meta["label"].upper())
            self.clear_btn.show()
        else:
            self.icon_lbl.setText("")
            self.name_lbl.setText("— пусто —")
            self.name_lbl.setStyleSheet("color:#8a8a99;font-size:10px;")
            self.cat_lbl.setText("")
            self.clear_btn.hide()
        self._apply_style(bool(sample), False)

    def _on_clear(self):
        """Отложенный emit — нельзя менять дерево виджетов внутри обработчика."""
        pid = self.pad_id
        QTimer.singleShot(0, lambda: self.cleared.emit(pid))

    def _apply_style(self, filled, drag_over):
        # Пропускаем, если состояние не изменилось — иначе лишние repaint
        key = (bool(filled), bool(drag_over))
        if getattr(self, "_style_key", None) == key:
            return
        self._style_key = key
        if drag_over:
            border, bg = "#06d6a0", "#16281f"
        elif filled:
            border, bg = "#ff5c38", "#2a2018"
        else:
            border, bg = "#2a2a34", "#23232d"
        self.setStyleSheet(
            f"QFrame{{background:{bg};border:2px solid {border};border-radius:12px;}}")

    # — drag over —
    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(MIME_SAMPLE):
            e.acceptProposedAction()
            self._apply_style(bool(self.sample), True)

    def dragLeaveEvent(self, e):
        self._apply_style(bool(self.sample), False)

    def dropEvent(self, e):
        if e.mimeData().hasFormat(MIME_SAMPLE):
            sid = bytes(e.mimeData().data(MIME_SAMPLE)).decode()
            e.acceptProposedAction()
            pid = self.pad_id
            # Откладываем: сигнал перестраивает UI, а мы внутри drag-loop
            QTimer.singleShot(0, lambda: self.assigned.emit(pid, sid))
        self._apply_style(bool(self.sample), False)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.sample:
            self.clicked.emit(self.pad_id)


# ─────────────────────────────────────────────
#  Список сэмплов с поддержкой drag
# ─────────────────────────────────────────────
class SampleList(QListWidget):
    play_requested   = Signal(str)        # sample_id
    delete_requested = Signal(str)        # sample_id

    def __init__(self):
        super().__init__()
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemDoubleClicked.connect(
            lambda it: self.play_requested.emit(it.data(Qt.UserRole)))

    def startDrag(self, actions):
        item = self.currentItem()
        if not item:
            return
        sid = item.data(Qt.UserRole)
        if not sid:                       # плейсхолдер-подсказка, не сэмпл
            return
        mime = QMimeData()
        mime.setData(MIME_SAMPLE, QByteArray(sid.encode()))
        drag = QDrag(self)
        drag.setMimeData(mime)
        # Держим ссылки: на macOS GC может убить объекты во время exec()
        self._drag_ref, self._mime_ref = drag, mime
        drag.exec(Qt.CopyAction)
        self._drag_ref = self._mime_ref = None

    def _menu(self, pos):
        item = self.itemAt(pos)
        if not item:
            return
        sid = item.data(Qt.UserRole)
        if not sid:
            return
        m = QMenu(self)
        m.addAction("▶  Прослушать", lambda: self.play_requested.emit(sid))
        m.addAction("🗑  Удалить",   lambda: self.delete_requested.emit(sid))
        m.exec(self.mapToGlobal(pos))


# ─────────────────────────────────────────────
#  Главное окно
# ─────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Каталоги создаём здесь, а не на импорте модуля: headless-тесты
        # и внешние скрипты конструируют окно напрямую, минуя main().
        ensure_app_dirs()
        self.setWindowTitle("SP-404SX Sample Manager — by SYNTX.AI")
        self.resize(1180, 780)
        self.setAcceptDrops(True)

        # состояние
        self.samples = {}                 # id -> sample dict
        self.assignments = {}             # pad_id -> sample_id
        self.cur_bank = "A"
        self.filter_cat = "all"
        self.pads = {}                    # pad_id -> PadWidget (текущий банк)
        self._thread = None
        self._worker = None

        # аудио-плеер
        self.player = QMediaPlayer()
        self.audio_out = QAudioOutput()
        self.player.setAudioOutput(self.audio_out)
        self.audio_out.setVolume(0.9)

        self._build_ui()
        self._load_project()
        self._build_bank_buttons()
        self._build_pads()
        self._render_bank_buttons()
        self._render_pads()
        self._render_samples()
        self._update_stats()

    # ── UI ──
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(12)

        # Заголовок
        header = QHBoxLayout()
        t = QLabel("🎛️  SP-404SX Sample Manager")
        t.setObjectName("title")
        header.addWidget(t)
        tag = QLabel("by SYNTX.AI")
        tag.setObjectName("tag")
        header.addWidget(tag)
        header.addStretch()
        lib_status = "✅ анализ вкл" if HAVE_LIBROSA else "⚠️ librosa нет"
        self.lib_lbl = QLabel(lib_status)
        self.lib_lbl.setObjectName("tag")
        header.addWidget(self.lib_lbl)
        root.addLayout(header)

        # Основная область: пэды | библиотека
        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        # ── Левая карточка: пэды ──
        left = QFrame(); left.setObjectName("card")
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(16, 14, 16, 14)

        pad_head = QHBoxLayout()
        h1 = QLabel("ПЭДЫ — БАНК"); h1.setObjectName("h2")
        pad_head.addWidget(h1)
        self.bank_name_lbl = QLabel("A")
        self.bank_name_lbl.setStyleSheet("color:#ff5c38;font-weight:700;font-size:14px;")
        pad_head.addWidget(self.bank_name_lbl)
        pad_head.addStretch()
        hint = QLabel("перетащи сэмпл на пэд →")
        hint.setObjectName("tag")
        pad_head.addWidget(hint)
        left_l.addLayout(pad_head)

        # Кнопки банков
        self.banks_lay = QHBoxLayout()
        self.banks_lay.setSpacing(5)
        left_l.addLayout(self.banks_lay)

        # Сетка пэдов 3×4 (12 пэдов, как на устройстве — снизу вверх)
        self.pad_grid = QGridLayout()
        self.pad_grid.setSpacing(12)
        grid_wrap = QWidget()
        grid_wrap.setLayout(self.pad_grid)
        left_l.addWidget(grid_wrap, 1)
        left_l.addStretch()

        body.addWidget(left, 1)

        # ── Правая карточка: библиотека ──
        right = QFrame(); right.setObjectName("card")
        right.setFixedWidth(380)
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(16, 14, 16, 14)

        h2 = QLabel("БИБЛИОТЕКА СЭМПЛОВ"); h2.setObjectName("h2")
        right_l.addWidget(h2)

        # Кнопки действий
        actions1 = QHBoxLayout()
        btn_add = QPushButton("📥  Добавить")
        btn_add.clicked.connect(self._pick_files)
        actions1.addWidget(btn_add)
        btn_auto = QPushButton("✨  Авто-раскладка")
        btn_auto.setObjectName("primary")
        btn_auto.clicked.connect(self._auto_assign)
        actions1.addWidget(btn_auto)
        right_l.addLayout(actions1)

        actions2 = QHBoxLayout()
        btn_clear = QPushButton("🗑  Очистить пэды")
        btn_clear.clicked.connect(self._clear_assignments)
        actions2.addWidget(btn_clear)
        btn_export = QPushButton("💾  Экспорт SD")
        btn_export.setObjectName("ok")
        btn_export.clicked.connect(self._export)
        actions2.addWidget(btn_export)
        right_l.addLayout(actions2)

        # Фильтр по категориям
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("Все категории", "all")
        for c in CATEGORY_ORDER:
            m = CATEGORY_META[c]
            self.filter_combo.addItem(f"{m['icon']}  {m['label']}", c)
        self.filter_combo.currentIndexChanged.connect(self._on_filter)
        right_l.addWidget(self.filter_combo)

        # Список сэмплов
        self.sample_list = SampleList()
        self.sample_list.play_requested.connect(self._play_sample)
        self.sample_list.delete_requested.connect(self._delete_sample)
        right_l.addWidget(self.sample_list, 1)

        # Прогресс-бар
        self.progress = QProgressBar()
        self.progress.hide()
        right_l.addWidget(self.progress)

        body.addWidget(right)

        # Статус-бар
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._flash("Готов. Перетащи аудиофайлы в окно или нажми «Добавить».")

    # ── Рендеринг ──
    def _build_bank_buttons(self):
        """Создаёт кнопки банков ОДИН раз. Пересоздание виджетов во время
        обработки событий приводит к segfault на macOS."""
        self.bank_btns = {}
        for b in BANKS:
            btn = QPushButton(b)
            btn.setFixedSize(34, 32)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, bb=b: self._switch_bank(bb))
            self.banks_lay.addWidget(btn)
            self.bank_btns[b] = btn
        self.banks_lay.addStretch()

    def _render_bank_buttons(self):
        """Обновляет только текст/стиль уже существующих кнопок."""
        for b, btn in self.bank_btns.items():
            cnt = sum(1 for p in self.assignments if p[0] == b)
            btn.setText(f"{b}·{cnt}" if cnt else b)
            active = (b == self.cur_bank)
            btn.setChecked(active)
            btn.setStyleSheet(
                "background:#ff5c38;border-color:#ff5c38;color:#fff;"
                if active else "")

    def _build_pads(self):
        """Создаёт 12 PadWidget ОДИН раз. При смене банка меняется только
        содержимое — иначе удаление виджетов во время события = segfault."""
        self.pads = {}
        self._pad_slots = []
        # Раскладка как на SP-404SX: пэды 1-3 снизу, 10-12 сверху
        for idx in range(PADS_PER_BANK):
            pad_num = idx + 1
            row = 3 - (idx // 3)         # инвертируем: 1-3 внизу
            col = idx % 3
            pw = PadWidget(f"{self.cur_bank}{pad_num}")
            pw.assigned.connect(self._assign)
            pw.cleared.connect(self._clear_pad)
            pw.clicked.connect(self._play_pad)
            self.pad_grid.addWidget(pw, row, col)
            self._pad_slots.append(pw)

    def _clear_pad(self, pad_id):
        self._assign(pad_id, None)

    def _render_pads(self):
        """Обновляет содержимое существующих пэдов (без пересоздания)."""
        self.pads = {}
        for idx, pw in enumerate(self._pad_slots):
            pad_num = idx + 1
            pad_id = f"{self.cur_bank}{pad_num}"
            pw.pad_id = pad_id
            pw.num_lbl.setText(str(pad_num))
            sid = self.assignments.get(pad_id)
            pw.set_sample(self.samples.get(sid) if sid else None)
            self.pads[pad_id] = pw

    def _render_samples(self):
        self.sample_list.clear()
        items = [s for s in self.samples.values()
                 if self.filter_cat == "all" or s["category"] == self.filter_cat]
        items.sort(key=lambda s: (s["category"], s["name"]))
        for s in items:
            meta = CATEGORY_META.get(s["category"], CATEGORY_META["unknown"])
            tempo = f" · {s['tempo']}bpm" if s.get("tempo") else ""
            text = f"{meta['icon']}  {s['name']}\n     {meta['label']} · {s['duration']}s{tempo}"
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, s["id"])
            self.sample_list.addItem(it)
        if not items:
            hint = "Загрузи сэмплы, чтобы начать 🎵" if not self.samples \
                   else "Нет сэмплов в этой категории"
            it = QListWidgetItem(hint)
            it.setFlags(Qt.NoItemFlags)
            self.sample_list.addItem(it)

    def _update_stats(self):
        n_s = len(self.samples)
        n_a = len(self.assignments)
        self.setWindowTitle(
            f"SP-404SX Sample Manager — {n_s} сэмплов · {n_a}/144 пэдов")
        self._render_bank_buttons()

    # ── Действия ──
    def _switch_bank(self, bank):
        self.cur_bank = bank
        self.bank_name_lbl.setText(bank)
        self._render_bank_buttons()
        self._render_pads()

    def _on_filter(self, idx):
        self.filter_cat = self.filter_combo.currentData()
        self._render_samples()

    def _assign(self, pad_id, sample_id):
        if sample_id is None:
            self.assignments.pop(pad_id, None)
            log.debug("Пэд %s очищен пользователем", pad_id)
            self._flash(f"Пэд {pad_id} очищен")
        else:
            if sample_id not in self.samples:
                log.warning("Попытка назначить несуществующий сэмпл %s на "
                            "пэд %s", sample_id, pad_id)
                return
            self.assignments[pad_id] = sample_id
            log.info("Назначено: «%s» -> %s",
                     self.samples[sample_id]["name"], pad_id)
            self._flash(f"«{self.samples[sample_id]['name']}» → {pad_id}")
        if pad_id in self.pads:
            sid = self.assignments.get(pad_id)
            self.pads[pad_id].set_sample(self.samples.get(sid) if sid else None)
        self._update_stats()
        self._save_project()

    def _auto_assign(self):
        if not self.samples:
            self._flash("⚠️ Нет сэмплов для раскладки")
            return
        log.info("Авто-раскладка: %d сэмплов", len(self.samples))
        self.assignments = auto_assign(self.samples, BANKS, PADS_PER_BANK)
        self._render_pads()
        self._update_stats()
        self._save_project()
        self._flash(f"✨ Разложено {len(self.assignments)} сэмплов по банкам")

    def _clear_assignments(self):
        if not self.assignments:
            return
        r = QMessageBox.question(self, "Очистить пэды",
                                 "Снять все назначения пэдов?")
        if r == QMessageBox.Yes:
            log.info("Пользователь очистил все назначения (%d пэдов)",
                     len(self.assignments))
            self.assignments = {}
            self._render_pads()
            self._update_stats()
            self._save_project()
            self._flash("Все пэды очищены")

    def _pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Выбрать аудио-сэмплы", str(Path.home()),
            "Аудио (*.wav *.aif *.aiff *.mp3 *.flac *.ogg)")
        if files:
            self._import_files(files)

    def _delete_sample(self, sid):
        s = self.samples.get(sid)
        if not s:
            return
        r = QMessageBox.question(self, "Удалить сэмпл",
                                 f"Удалить «{s['name']}» из проекта?")
        if r != QMessageBox.Yes:
            return
        log.info("Удаление сэмпла «%s»", s["name"])
        self.samples.pop(sid, None)
        try:
            Path(s["path"]).unlink(missing_ok=True)
        except Exception:
            # Файл на диске не удалился (нет прав, уже удалён извне) —
            # проект всё равно продолжит без него, но раньше это было
            # совершенно незаметно даже при повторяющемся сбое.
            log.warning("Не удалось удалить файл %s с диска", s["path"],
                        exc_info=True)
        self.assignments = {p: v for p, v in self.assignments.items() if v != sid}
        self._render_pads()
        self._render_samples()
        self._update_stats()
        self._save_project()

    # ── Аудио ──
    def _play_sample(self, sid):
        s = self.samples.get(sid)
        if not s:
            return
        if not Path(s["path"]).exists():
            # Раньше клик по пропавшему файлу просто ничего не делал —
            # пользователь не понимал, почему сэмпл не звучит.
            log.warning("Файл сэмпла «%s» отсутствует на диске: %s",
                        s["name"], s["path"])
            self._flash(f"⚠️ Файл «{s['name']}» не найден на диске")
            return
        log.debug("Воспроизведение: %s", s["name"])
        self.player.setSource(QUrl.fromLocalFile(s["path"]))
        self.player.play()

    def _play_pad(self, pad_id):
        sid = self.assignments.get(pad_id)
        if sid:
            self._play_sample(sid)

    # ── Импорт (в фоне) ──
    def _import_files(self, filepaths):
        if self._thread and self._thread.isRunning():
            self._flash("⏳ Дождись окончания текущей операции")
            return
        log.info("Запуск импорта: %d файл(ов)", len(filepaths))
        self.progress.setRange(0, len(filepaths))
        self.progress.setValue(0)
        self.progress.show()
        self._flash(f"⏳ Анализирую {len(filepaths)} файл(ов)…")

        self._thread = QThread()
        self._worker = AnalyzeWorker(filepaths)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.one_done.connect(self._on_sample_added)
        self._worker.progress.connect(lambda d, t: self.progress.setValue(d))
        self._worker.finished.connect(self._on_import_done)
        self._worker.failed.connect(self._on_worker_failed)
        self._thread.start()

    def _on_sample_added(self, sample):
        self.samples[sample["id"]] = sample
        self._render_samples()
        self._update_stats()

    def _on_import_done(self, added):
        self._thread.quit()
        self._thread.wait()
        self.progress.hide()
        self._save_project()
        self._flash(f"✅ Добавлено {added} сэмплов")

    # ── Экспорт (в фоне) ──
    def _export(self):
        if not self.assignments:
            self._flash("⚠️ Нет назначенных пэдов")
            return
        out = QFileDialog.getExistingDirectory(
            self, "Куда экспортировать (структура ROLAND/… создастся внутри)",
            str(Path.home()))
        if not out:
            return
        out_dir = Path(out) / "SP-404SX_SD"
        log.info("Запуск экспорта: %d пэдов -> %s",
                 len(self.assignments), out_dir)

        self.progress.setRange(0, len(self.assignments))
        self.progress.setValue(0)
        self.progress.show()
        self._flash("⏳ Экспортирую и конвертирую в 44.1kHz/16-bit…")

        self._thread = QThread()
        self._worker = ExportWorker(dict(self.assignments), dict(self.samples),
                                    out_dir, make_zip=True)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(lambda d, t: self.progress.setValue(d))
        self._worker.finished.connect(self._on_export_done)
        self._worker.failed.connect(self._on_worker_failed)
        self._thread.start()

    def _on_export_done(self, result):
        self._thread.quit()
        self._thread.wait()
        self.progress.hide()
        n = len(result["exported"])
        errs = result["errors"]
        log.info("Экспорт завершён: %d сэмплов, %d ошибок", n, len(errs))
        msg = f"💾 Экспортировано {n} сэмплов."
        if result.get("zip"):
            msg += f"\n\nZIP: {result['zip']}"
        if errs:
            msg += f"\n\n⚠️ Ошибок: {len(errs)}\n" + "\n".join(errs[:5])
        QMessageBox.information(self, "Экспорт завершён", msg)
        self._flash(f"✅ Экспортировано {n} сэмплов в формат SP-404SX")

    def _on_worker_failed(self, message):
        """Общий обработчик сигнала failed от AnalyzeWorker/ExportWorker.

        Без этого слота непойманное исключение в воркере (см. защиту в
        run()) оставляло бы прогресс-бар висеть навечно: finished в этом
        случае не эмитится, поток остаётся "выполняющимся" для GUI.
        Полный traceback уже записан воркером через log.exception —
        здесь только приводим интерфейс в консистентное состояние.
        """
        log.error("Фоновая операция прервана ошибкой: %s", message)
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        self.progress.hide()
        self._flash(f"❌ Ошибка: {message}")
        QMessageBox.critical(
            self, "Ошибка фоновой операции",
            f"Операция не завершилась из-за непредвиденной ошибки:\n\n{message}\n\n"
            f"Подробности записаны в файл лога.")

    # ── Drag & drop файлов в окно ──
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = []
        for url in e.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXT:
                paths.append(str(p))
            elif p.is_dir():
                for f in p.rglob("*"):
                    if f.suffix.lower() in SUPPORTED_EXT:
                        paths.append(str(f))
        log.debug("Drag&drop: %d файл(ов) распознано", len(paths))
        if paths:
            self._import_files(paths)

    # ── Проект ──
    def _save_project(self):
        data = {"samples": self.samples, "assignments": self.assignments,
                "saved": datetime.now().isoformat()}
        try:
            with open(PROJECT_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            # Это худший из тихих сбоев в приложении: пользователь
            # продолжает работать, уверенный, что проект сохраняется,
            # а на деле каждое изменение теряется молча. _save_project
            # вызывается после почти любого действия (импорт, назначение,
            # удаление) — раньше ни одно из них не оставляло следа при сбое.
            log.exception("Не удалось сохранить проект в %s", PROJECT_FILE)

    def _load_project(self):
        if not PROJECT_FILE.exists():
            log.debug("Файл проекта не найден (%s) — старт с пустого проекта",
                      PROJECT_FILE)
            return
        try:
            with open(PROJECT_FILE, encoding="utf-8") as f:
                data = json.load(f)
            # оставляем только существующие файлы
            samples = {k: v for k, v in data.get("samples", {}).items()
                      if Path(v["path"]).exists()}
            missing = len(data.get("samples", {})) - len(samples)
            self.samples = samples
            self.assignments = {p: s for p, s in data.get("assignments", {}).items()
                                if s in self.samples}
            log.info("Проект загружен: %d сэмплов, %d назначений%s",
                     len(self.samples), len(self.assignments),
                     f" ({missing} файл(ов) не найдено на диске)" if missing else "")
        except Exception:
            # Раньше битый/несовместимый project.json приводил к тихому
            # старту с пустым проектом — пользователь терял весь список
            # сэмплов и назначений без единого объяснения почему.
            log.exception("Не удалось загрузить проект из %s — "
                          "продолжаю с пустым проектом", PROJECT_FILE)

    def _flash(self, msg):
        log.debug("[статус] %s", msg)
        self.status.showMessage(msg, 5000)


# ─────────────────────────────────────────────────────────────────────
#  Глобальные перехватчики ошибок
# ─────────────────────────────────────────────────────────────────────
_QT_MSG_LEVELS = {
    QtMsgType.QtDebugMsg:    logging.DEBUG,
    QtMsgType.QtInfoMsg:     logging.INFO,
    QtMsgType.QtWarningMsg:  logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg:    logging.CRITICAL,
}


def _qt_message_handler(mode, context, message):
    """Перенаправляет диагностику Qt в logging.

    Предупреждения Qt (проблемы компоновки, отсутствующие мультимедиа-
    бэкенды, ошибки QMediaPlayer) писались прямо в stderr и в собранном
    .app пропадали бесследно.
    """
    level = _QT_MSG_LEVELS.get(mode, logging.INFO)
    where = ""
    if context is not None and getattr(context, "file", None):
        where = f" ({context.file}:{context.line})"
    _qt_log.log(level, "%s%s", message, where)


def _show_crash_dialog(exc_value) -> None:
    """Показывает пользователю диалог о сбое с путём к файлу лога."""
    try:
        if QApplication.instance() is None:
            return
        log_path = get_log_file()
        box = QMessageBox()
        box.setIcon(QMessageBox.Critical)
        box.setWindowTitle("Непредвиденная ошибка")
        box.setText("Произошла непредвиденная ошибка.\n"
                    "Приложение продолжит работу, но состояние может быть "
                    "некорректным.")
        box.setInformativeText(f"{type(exc_value).__name__}: {exc_value}")
        if log_path:
            box.setDetailedText(f"Подробности записаны в лог:\n{log_path}")
        box.exec()
    except Exception:
        # Диалог — не критичный путь: traceback уже в логе.
        log.exception("Не удалось показать диалог об ошибке")


def _excepthook(exc_type, exc_value, exc_tb):
    """sys.excepthook — необработанные исключения главного потока."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    log.critical("Необработанное исключение в главном потоке",
                 exc_info=(exc_type, exc_value, exc_tb))
    _show_crash_dialog(exc_value)


def _thread_excepthook(args):
    """threading.excepthook — необработанные исключения фоновых потоков.

    Внимание: QThread создаётся средствами Qt, а не модулем threading,
    поэтому падение внутри AnalyzeWorker.run/ExportWorker.run этот хук
    перехватит не во всех сборках PySide6. Надёжная защита воркеров —
    явный try/except в самих run() (шаг 4). Хук оставлен как страховка
    и покрывает обычные threading.Thread.
    """
    if issubclass(args.exc_type, SystemExit):
        return
    log.critical("Необработанное исключение в потоке %s",
                 getattr(args.thread, "name", "?"),
                 exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def install_error_handlers() -> None:
    """Ставит перехватчики. Вызывать один раз, до создания QApplication."""
    sys.excepthook = _excepthook
    if hasattr(threading, "excepthook"):        # Python 3.8+
        threading.excepthook = _thread_excepthook
    qInstallMessageHandler(_qt_message_handler)
    log.debug("Глобальные перехватчики ошибок установлены")


# ─────────────────────────────────────────────────────────────────────
#  Точка входа
# ─────────────────────────────────────────────────────────────────────
def _default_font_family() -> str:
    """Системный шрифт под текущую ОС (на macOS нет 'Segoe UI')."""
    plat = get_platform()
    if plat == "macos":
        return "Helvetica Neue"
    if plat == "windows":
        return "Segoe UI"
    return "Ubuntu"


def main():
    # Логирование поднимаем самым первым — до Qt, до создания каталогов,
    # чтобы любой последующий сбой оказался в файле.
    setup_logging()
    log_system_info()
    install_error_handlers()
    ensure_app_dirs()

    log.info("Запуск приложения")
    app = QApplication(sys.argv)
    app.setApplicationName("SP-404SX Sample Manager")
    app.setApplicationDisplayName("SP-404SX Sample Manager")

    font = QFont(_default_font_family())
    app.setFont(font)

    app.setStyleSheet(STYLESHEET)
    win = MainWindow()
    win.show()

    log.info("Главное окно показано, вход в цикл событий")
    rc = app.exec()
    log.info("Цикл событий завершён, код возврата=%s", rc)
    shutdown_logging()
    sys.exit(rc)


if __name__ == "__main__":
    main()
