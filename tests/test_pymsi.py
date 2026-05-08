import io
import struct
import warnings

import pytest

import pymsi
from pymsi.column import Column
from pymsi.reader import BinaryReader
from pymsi.table import Table


class _FakeStream:
    """Minimal stream that satisfies BinaryReader's interface (mirrors OleStream API)."""

    def __init__(self, data: bytes):
        self._bio = io.BytesIO(data)
        self.size = len(data)  # OleStream exposes size as an attribute

    def read(self, n=-1):
        return self._bio.read(n)

    def tell(self):
        return self._bio.tell()

    def seek(self, pos):
        self._bio.seek(pos)


class _FakeStringPool:
    """Minimal string pool for use with integer-only tables (no string columns)."""

    long_string_refs = False


def _make_int_table():
    """Create a table with two i16 columns (row_size=4, no string pool needed)."""
    return Table("TestTable", [Column("A").i16(), Column("B").i16()])


def test_version():
    assert pymsi.__version__


def test_read_rows_strict_raises_on_bad_length():
    """Table._read_rows raises ValueError in strict mode when data length is not a multiple of row size."""
    table = _make_int_table()  # row_size = 4
    # 9 bytes: 2 complete rows (8 bytes) + 1 leftover byte
    data = struct.pack("<hh", 1, 2) + struct.pack("<hh", 3, 4) + b"\x00"
    reader = BinaryReader(_FakeStream(data))
    with pytest.raises(ValueError, match="not a multiple of row size"):
        table._read_rows(reader, _FakeStringPool(), strict=True)


def test_read_rows_non_strict_warns_and_returns_complete_rows():
    """Table._read_rows emits a UserWarning in non-strict mode and returns only complete rows."""
    table = _make_int_table()  # row_size = 4
    # 9 bytes: 2 complete rows (8 bytes) + 1 leftover byte
    data = struct.pack("<hh", 1, 2) + struct.pack("<hh", 3, 4) + b"\x00"
    reader = BinaryReader(_FakeStream(data))
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        rows = table._read_rows(reader, _FakeStringPool(), strict=False)
    assert len(w) == 1
    assert issubclass(w[0].category, UserWarning)
    assert "trailing bytes" in str(w[0].message).lower()
    assert len(rows) == 2  # only 2 complete rows; leftover byte is ignored


def test_read_rows_non_strict_partial_less_than_one_row():
    """Table._read_rows in non-strict mode returns an empty list when there are zero complete rows.

    This mirrors the QGIS MSI Icon table scenario: the stream has 5 bytes but the row
    size is 6, yielding zero complete rows (5 // 6 == 0), so all 5 bytes are trailing.
    """
    table = _make_int_table()  # row_size = 4
    # 3 bytes < row_size (4): zero complete rows, all bytes are trailing
    data = b"\x89\xc4\x02"
    reader = BinaryReader(_FakeStream(data))
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        rows = table._read_rows(reader, _FakeStringPool(), strict=False)
    assert len(w) == 1
    assert issubclass(w[0].category, UserWarning)
    assert len(rows) == 0  # no complete rows; all 3 bytes are trailing
