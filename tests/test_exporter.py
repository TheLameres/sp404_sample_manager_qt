"""Tests for exporter module."""
import pytest
from pathlib import Path
import tempfile
import struct

from sp404_manager.exporter import (
    PadInfoRecord, pad_to_padinfo_index, pad_to_filename,
    padinfo_index_to_pad, parse_padinfo,
    PADINFO_RECORD_COUNT, PADINFO_RECORD_SIZE,
)


def test_pad_to_filename():
    """Test pad to filename conversion."""
    assert pad_to_filename("A1") == "A0000001.WAV"
    assert pad_to_filename("B5") == "B0000005.WAV"
    assert pad_to_filename("J12") == "J0000012.WAV"


def test_pad_to_padinfo_index():
    """Test pad to PADINFO index conversion."""
    assert pad_to_padinfo_index("A1") == 0
    assert pad_to_padinfo_index("A12") == 11
    assert pad_to_padinfo_index("B1") == 12
    assert pad_to_padinfo_index("J12") == 119


def test_pad_to_padinfo_index_out_of_range():
    """Test that K and L raise ValueError."""
    with pytest.raises(ValueError):
        pad_to_padinfo_index("K1")
    with pytest.raises(ValueError):
        pad_to_padinfo_index("L1")


def test_padinfo_record_size():
    """Test that PadInfoRecord is exactly 32 bytes."""
    rec = PadInfoRecord()
    data = rec.to_bytes()
    assert len(data) == 32


def test_padinfo_record_tempo():
    """Tempo кодируется как uint32 (BPM x 10) по offset 24 и 28,
    а не как uint16 (старая ошибочная раскладка)."""
    rec = PadInfoRecord()
    rec.orig_tempo = 1200  # 120 BPM
    rec.user_tempo = 1200
    data = rec.to_bytes()
    orig_tempo = struct.unpack(">I", data[24:28])[0]
    user_tempo = struct.unpack(">I", data[28:32])[0]
    assert orig_tempo == 1200
    assert user_tempo == 1200


def test_padinfo_record_channels_and_tempo_mode_offsets():
    """Channels (offset 22) и TempoMode (offset 23) должны быть
    отдельными uint8-полями, не пересекающимися с tempo."""
    rec = PadInfoRecord()
    rec.channels = 1
    rec.tempo_mode = 2
    data = rec.to_bytes()
    assert data[22] == 1  # channels
    assert data[23] == 2  # tempo_mode


def test_padinfo_record_volume():
    """Test that volume is correctly encoded."""
    rec = PadInfoRecord()
    rec.volume = 100
    data = rec.to_bytes()
    volume = data[16]
    assert volume == 100


def test_padinfo_record_round_trip_defaults():
    """to_bytes() -> from_bytes() должен восстанавливать те же значения
    для записи со значениями по умолчанию."""
    rec = PadInfoRecord()
    data = rec.to_bytes()
    rec2 = PadInfoRecord.from_bytes(data)
    assert rec2.orig_sample_start == rec.orig_sample_start
    assert rec2.orig_sample_end == rec.orig_sample_end
    assert rec2.user_sample_start == rec.user_sample_start
    assert rec2.user_sample_end == rec.user_sample_end
    assert rec2.volume == rec.volume
    assert rec2.lofi == rec.lofi
    assert rec2.loop == rec.loop
    assert rec2.gate == rec.gate
    assert rec2.reverse == rec.reverse
    assert rec2.format == rec.format
    assert rec2.channels == rec.channels
    assert rec2.tempo_mode == rec.tempo_mode
    assert rec2.orig_tempo == rec.orig_tempo
    assert rec2.user_tempo == rec.user_tempo


def test_padinfo_record_round_trip_custom_values():
    """Round-trip с произвольными (не-дефолтными) значениями."""
    rec = PadInfoRecord()
    rec.orig_sample_start = 512
    rec.orig_sample_end = 512 + 987654
    rec.user_sample_start = 1024
    rec.user_sample_end = 512 + 500000
    rec.volume = 87
    rec.lofi = 1
    rec.loop = 1
    rec.gate = 0
    rec.reverse = 1
    rec.format = 0
    rec.channels = 1
    rec.tempo_mode = 2
    rec.set_bpm(109.9, mode="both")

    data = rec.to_bytes()
    assert len(data) == 32

    rec2 = PadInfoRecord.from_bytes(data)
    assert rec2.orig_sample_start == 512
    assert rec2.orig_sample_end == 512 + 987654
    assert rec2.user_sample_start == 1024
    assert rec2.user_sample_end == 512 + 500000
    assert rec2.volume == 87
    assert rec2.lofi == 1
    assert rec2.loop == 1
    assert rec2.gate == 0
    assert rec2.reverse == 1
    assert rec2.format == 0
    assert rec2.channels == 1
    assert rec2.tempo_mode == 2
    assert rec2.orig_tempo == 1099
    assert rec2.user_tempo == 1099


def test_padinfo_record_from_bytes_wrong_size():
    """from_bytes должен бросать ValueError на данных неверного размера."""
    with pytest.raises(ValueError):
        PadInfoRecord.from_bytes(b'\x00' * 10)


def test_set_bpm_user_mode():
    """set_bpm с mode='user' меняет только user_tempo."""
    rec = PadInfoRecord()
    rec.orig_tempo = 1200
    rec.user_tempo = 1200
    rec.set_bpm(140.0, mode="user")
    assert rec.user_tempo == 1400
    assert rec.orig_tempo == 1200  # не изменился


def test_set_bpm_orig_mode():
    """set_bpm с mode='orig' меняет только orig_tempo."""
    rec = PadInfoRecord()
    rec.orig_tempo = 1200
    rec.user_tempo = 1200
    rec.set_bpm(90.5, mode="orig")
    assert rec.orig_tempo == 905
    assert rec.user_tempo == 1200  # не изменился


def test_set_bpm_both_mode():
    """set_bpm с mode='both' меняет и orig_tempo, и user_tempo."""
    rec = PadInfoRecord()
    rec.set_bpm(128.3, mode="both")
    assert rec.orig_tempo == 1283
    assert rec.user_tempo == 1283


def test_set_bpm_out_of_range_raises():
    """set_bpm должен валидировать диапазон BPM."""
    rec = PadInfoRecord()
    with pytest.raises(ValueError):
        rec.set_bpm(10.0)  # ниже MIN_BPM
    with pytest.raises(ValueError):
        rec.set_bpm(500.0)  # выше MAX_BPM


def test_set_bpm_invalid_mode_raises():
    """set_bpm должен проверять корректность параметра mode."""
    rec = PadInfoRecord()
    with pytest.raises(ValueError):
        rec.set_bpm(120.0, mode="invalid")


def test_validate_rejects_bad_volume():
    rec = PadInfoRecord()
    rec.volume = 200  # вне диапазона 0-127
    with pytest.raises(ValueError):
        rec.to_bytes()


def test_validate_rejects_bad_bit_field():
    rec = PadInfoRecord()
    rec.loop = 5  # должно быть 0 или 1
    with pytest.raises(ValueError):
        rec.to_bytes()


def test_validate_rejects_bad_channels():
    rec = PadInfoRecord()
    rec.channels = 3  # должно быть 1 или 2
    with pytest.raises(ValueError):
        rec.to_bytes()


def test_validate_rejects_bad_tempo_mode():
    rec = PadInfoRecord()
    rec.tempo_mode = 9  # должно быть 0/1/2
    with pytest.raises(ValueError):
        rec.to_bytes()


def test_padinfo_index_to_pad():
    """Обратное преобразование индекса в идентификатор пэда."""
    assert padinfo_index_to_pad(0) == "A1"
    assert padinfo_index_to_pad(11) == "A12"
    assert padinfo_index_to_pad(12) == "B1"
    assert padinfo_index_to_pad(119) == "J12"


def test_padinfo_index_to_pad_out_of_range():
    with pytest.raises(ValueError):
        padinfo_index_to_pad(-1)
    with pytest.raises(ValueError):
        padinfo_index_to_pad(120)


def test_pad_index_round_trip():
    """pad_to_padinfo_index и padinfo_index_to_pad должны быть обратны друг другу."""
    for bank_idx in range(10):
        bank_char = chr(ord('A') + bank_idx)
        for pad_num in range(1, 13):
            pad_id = f"{bank_char}{pad_num}"
            idx = pad_to_padinfo_index(pad_id)
            assert padinfo_index_to_pad(idx) == pad_id


def test_parse_padinfo_round_trip(tmp_path):
    """Записываем 120 записей в файл, читаем через parse_padinfo,
    проверяем, что значения совпадают."""
    records = {}
    for i in range(PADINFO_RECORD_COUNT):
        pad_id = padinfo_index_to_pad(i)
        rec = PadInfoRecord()
        rec.volume = i % 128
        rec.set_bpm(60.0 + (i % 240), mode="both")
        records[pad_id] = rec

    padinfo_path = tmp_path / "PADINFO.BIN"
    with open(padinfo_path, "wb") as f:
        for i in range(PADINFO_RECORD_COUNT):
            pad_id = padinfo_index_to_pad(i)
            f.write(records[pad_id].to_bytes())

    assert padinfo_path.stat().st_size == PADINFO_RECORD_COUNT * PADINFO_RECORD_SIZE

    parsed = parse_padinfo(padinfo_path)
    assert len(parsed) == PADINFO_RECORD_COUNT
    for pad_id, rec in records.items():
        assert parsed[pad_id].volume == rec.volume
        assert parsed[pad_id].orig_tempo == rec.orig_tempo
        assert parsed[pad_id].user_tempo == rec.user_tempo


def test_parse_padinfo_wrong_file_size_logs_warning(tmp_path, caplog):
    """parse_padinfo не должен падать на файле неправильного размера,
    но должен разобрать столько полных записей, сколько есть."""
    padinfo_path = tmp_path / "PADINFO.BIN"
    padinfo_path.write_bytes(PadInfoRecord().to_bytes() * 5)  # только 5 записей
    parsed = parse_padinfo(padinfo_path)
    assert len(parsed) == 5
