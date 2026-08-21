"""Tests for exporter module."""
import pytest
from pathlib import Path
import tempfile
import struct

from sp404_manager.exporter import (
    PadInfoRecord, pad_to_padinfo_index, pad_to_filename
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
    """Test that tempo is correctly encoded."""
    rec = PadInfoRecord()
    rec.orig_tempo = 1200  # 120 BPM
    data = rec.to_bytes()
    tempo = struct.unpack(">H", data[22:24])[0]
    assert tempo == 1200


def test_padinfo_record_volume():
    """Test that volume is correctly encoded."""
    rec = PadInfoRecord()
    rec.volume = 100
    data = rec.to_bytes()
    volume = data[16]
    assert volume == 100
