"""Тесты для PadInfoEditorDialog и связанной логики MainWindow.

Требуют оффскрин Qt-платформу — задаём переменную окружения перед
любыми импортами PySide6/sp404_manager.main.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil
from pathlib import Path

import pytest

# QApplication нужен один на процесс — создаём фикстурой сессии
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def clean_app_dir(tmp_path, monkeypatch):
    """Изолирует APP_DIR/PROJECT_FILE от реального ~/.sp404_manager."""
    import sp404_manager.main as M
    app_dir = tmp_path / ".sp404_manager"
    samples_dir = app_dir / "samples"
    project_file = app_dir / "project.json"
    monkeypatch.setattr(M, "APP_DIR", app_dir)
    monkeypatch.setattr(M, "SAMPLES_DIR", samples_dir)
    monkeypatch.setattr(M, "PROJECT_FILE", project_file)
    yield M
    if app_dir.exists():
        shutil.rmtree(app_dir)


def test_padinfo_editor_dialog_default_values(qapp):
    """Диалог должен подхватывать значения из переданной PadInfoRecord."""
    from sp404_manager.main import PadInfoEditorDialog
    from sp404_manager.exporter import PadInfoRecord

    rec = PadInfoRecord()
    rec.set_bpm(95.5, mode="both")
    rec.volume = 100
    rec.loop = 1
    rec.gate = 0
    rec.reverse = 1
    rec.lofi = 1

    dlg = PadInfoEditorDialog("B3", "snare.wav", rec)
    assert dlg.bpm_spin.value() == pytest.approx(95.5)
    assert dlg.volume_spin.value() == 100
    assert dlg.loop_check.isChecked() is True
    assert dlg.gate_check.isChecked() is False
    assert dlg.reverse_check.isChecked() is True
    assert dlg.lofi_check.isChecked() is True


def test_padinfo_editor_dialog_get_values_encodes_bpm(qapp):
    """get_values() должен конвертировать BPM в uint32 (BPM x 10)
    и упаковывать в orig_tempo/user_tempo — совместимо с PadInfoRecord."""
    from sp404_manager.main import PadInfoEditorDialog
    from sp404_manager.exporter import PadInfoRecord

    rec = PadInfoRecord()
    dlg = PadInfoEditorDialog("A1", "kick.wav", rec)
    dlg.bpm_spin.setValue(140.0)
    dlg.volume_spin.setValue(90)
    dlg.loop_check.setChecked(True)
    dlg.gate_check.setChecked(False)
    dlg.reverse_check.setChecked(True)
    dlg.lofi_check.setChecked(False)

    values = dlg.get_values()
    assert values["orig_tempo"] == 1400
    assert values["user_tempo"] == 1400
    assert values["volume"] == 90
    assert values["loop"] == 1
    assert values["gate"] == 0
    assert values["reverse"] == 1
    assert values["lofi"] == 0


def test_padinfo_editor_dialog_values_apply_cleanly_to_record(qapp):
    """Значения из get_values() должны без ошибок применяться через
    setattr к PadInfoRecord и проходить validate()/to_bytes()."""
    from sp404_manager.main import PadInfoEditorDialog
    from sp404_manager.exporter import PadInfoRecord

    rec = PadInfoRecord()
    dlg = PadInfoEditorDialog("C5", "loop.wav", rec)
    dlg.bpm_spin.setValue(174.2)
    values = dlg.get_values()

    target = PadInfoRecord()
    for k, v in values.items():
        assert hasattr(target, k), f"PadInfoRecord не имеет атрибута {k}"
        setattr(target, k, v)

    data = target.to_bytes()  # бросит ValueError, если что-то не так
    assert len(data) == 32

    restored = PadInfoRecord.from_bytes(data)
    assert restored.orig_tempo == 1742
    assert restored.user_tempo == 1742


def test_main_window_edit_pad_info_stores_override(qapp, clean_app_dir):
    """_edit_pad_info должен сохранять переопределения в
    self.padinfo_overrides без открытия модального диалога
    (эмулируем через прямой вызов внутренней логики)."""
    from sp404_manager.main import MainWindow, PadInfoEditorDialog
    from PySide6.QtWidgets import QDialog

    win = MainWindow()
    try:
        assert win.padinfo_overrides == {}

        # Подменяем exec(), чтобы не блокировать тест модальным окном
        def fake_exec(self):
            self.bpm_spin.setValue(133.3)
            self.gate_check.setChecked(False)
            return QDialog.Accepted

        orig_exec = PadInfoEditorDialog.exec
        PadInfoEditorDialog.exec = fake_exec
        try:
            win._edit_pad_info("A1")
        finally:
            PadInfoEditorDialog.exec = orig_exec

        assert "A1" in win.padinfo_overrides
        assert win.padinfo_overrides["A1"]["orig_tempo"] == 1333
        assert win.padinfo_overrides["A1"]["user_tempo"] == 1333
        assert win.padinfo_overrides["A1"]["gate"] == 0
    finally:
        win.deleteLater()


def test_main_window_project_round_trip_with_overrides(qapp, clean_app_dir):
    """padinfo_overrides должны сохраняться в project.json и
    восстанавливаться при следующей загрузке проекта."""
    from sp404_manager.main import MainWindow

    win = MainWindow()
    win.padinfo_overrides["B7"] = {
        "volume": 64, "loop": 1, "gate": 0, "reverse": 0, "lofi": 1,
        "orig_tempo": 998, "user_tempo": 998,
    }
    win._save_project()
    win.deleteLater()

    win2 = MainWindow()
    try:
        assert win2.padinfo_overrides.get("B7") == {
            "volume": 64, "loop": 1, "gate": 0, "reverse": 0, "lofi": 1,
            "orig_tempo": 998, "user_tempo": 998,
        }
    finally:
        win2.deleteLater()


def test_export_worker_forwards_padinfo_records(qapp, tmp_path):
    """ExportWorker должен передавать padinfo_records в export_sd(),
    и итоговый PADINFO.BIN должен содержать заданные значения."""
    import wave
    import numpy as np

    from sp404_manager.main import ExportWorker
    from sp404_manager.exporter import parse_padinfo

    # Готовим минимальный сэмпл
    sample_path = tmp_path / "kick.wav"
    sr = 44100
    t = np.linspace(0, 0.2, int(sr * 0.2))
    y = (np.sin(2 * np.pi * 60 * t) * 0.5 * 32767).astype("<i2")
    with wave.open(str(sample_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(y.tobytes())

    samples = {"s1": {"id": "s1", "name": "kick.wav", "path": str(sample_path),
                       "category": "kick", "duration": 0.2, "tempo": 0}}
    assignments = {"A1": "s1"}
    overrides = {"A1": {"volume": 55, "loop": 1, "gate": 0, "reverse": 1,
                         "lofi": 0, "orig_tempo": 1500, "user_tempo": 1500}}

    out_dir = tmp_path / "SP-404SX_SD"
    worker = ExportWorker(assignments, samples, out_dir, make_zip=False,
                           padinfo_records=overrides)
    worker.run()

    padinfo_path = out_dir / "ROLAND" / "SP-404SX" / "SMPL" / "PADINFO.BIN"
    assert padinfo_path.exists()

    parsed = parse_padinfo(padinfo_path)
    rec = parsed["A1"]
    assert rec.volume == 55
    assert rec.loop == 1
    assert rec.gate == 0
    assert rec.reverse == 1
    assert rec.lofi == 0
    assert rec.orig_tempo == 1500
    assert rec.user_tempo == 1500
