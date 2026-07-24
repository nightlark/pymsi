# ---------------------------------------------------------------------------
# Regression tests for binary (object/stream) columns as observed with QGIS installers.
# May have significant overlap with test_binary_columns.py
# Root cause of https://github.com/nightlark/pymsi/issues/160: binary columns
# (e.g. Icon.Data, type bits 0x0900, declared "v0") are always 2 bytes on disk,
# even when the string pool uses 3-byte long string refs. pymsi treated them as
# string refs, computing row_size=6 for the Icon table when the on-disk row is
# actually 5 bytes (3-byte Name ref + 2-byte Data marker).
# Reference: Wine dlls/msi/table.c bytes_per_column() and rust-msi column.rs.
# ---------------------------------------------------------------------------

import io
import struct

import pytest

from pymsi.column import Column
from pymsi.reader import BinaryReader
from pymsi.stringpool import StringPool
from pymsi.table import Table


class _FakeStream:
    """Minimal stream satisfying BinaryReader's interface (mirrors OleStream)."""

    def __init__(self, data: bytes):
        self._bio = io.BytesIO(data)
        self.size = len(data)  # OleStream exposes size as an attribute

    def read(self, n=-1):
        return self._bio.read(n)

    def tell(self):
        return self._bio.tell()

    def seek(self, pos):
        self._bio.seek(pos)


def _make_string_pool(strings, long_refs: bool):
    """Build a real StringPool from synthetic _StringPool/_StringData streams."""
    codepage = 1252 | (0x8000_0000 if long_refs else 0)
    pool = struct.pack("<I", codepage)
    data = b""
    for s in strings:
        raw = s.encode("cp1252")
        pool += struct.pack("<HH", len(raw), 1)
        data += raw
    return StringPool(_FakeStream(pool), _FakeStream(data))


ICON_TYPE_BITS_NAME = 0x2D48  # s72, primary key (observed in QGIS MSIs)
ICON_TYPE_BITS_DATA = 0x0900  # v0 binary column (observed in QGIS MSIs)


def _make_icon_table():
    return Table(
        "Icon",
        [
            Column("Name", ICON_TYPE_BITS_NAME),
            Column("Data", ICON_TYPE_BITS_DATA),
        ],
    )


def test_binary_column_type_detection():
    col = Column("Data", ICON_TYPE_BITS_DATA)
    assert col.type == "binary"
    # Nullable binary columns are still binary (Wine masks MSITYPE_NULLABLE)
    col = Column("Data", ICON_TYPE_BITS_DATA | 0x1000)
    assert col.type == "binary"
    # Regular string columns are unaffected
    col = Column("Name", ICON_TYPE_BITS_NAME)
    assert col.type == "str"


def test_binary_column_width_ignores_long_string_refs():
    """Binary columns are 2 bytes on disk regardless of string-ref width
    (Wine table.c bytes_per_column: MSITYPE_IS_BINARY -> 2)."""
    col = Column("Data", ICON_TYPE_BITS_DATA)
    assert col.width(long_string_refs=False) == 2
    assert col.width(long_string_refs=True) == 2


def test_icon_table_row_size_with_long_string_refs():
    table = _make_icon_table()
    pool = _make_string_pool(["icon.ico"], long_refs=True)
    row_size = sum(c.width(pool.long_string_refs) for c in table.columns)
    assert row_size == 5  # 3-byte string ref + 2-byte binary marker


def test_icon_table_qgis_scenario_parses_one_row():
    """Reproduces the exact on-disk layout of the QGIS Icon table: a 5-byte
    stream under long string refs holding one row ('icon.ico', present)."""
    table = _make_icon_table()
    pool = _make_string_pool(["icon.ico"], long_refs=True)
    # Column-major stream: Name strref (3 bytes, ref 1 -> first string) then
    # Data cell (2 bytes, 1 = data present). QGIS 3.40.15's actual stream is
    # 89 c4 02 01 00 with ref 181385; here the pool has one string so ref=1.
    data = struct.pack("<HB", 1, 0) + struct.pack("<H", 1)
    assert len(data) == 5
    rows = table._read_rows(BinaryReader(_FakeStream(data)), pool)  # strict default
    assert rows == [{"Name": "icon.ico", "Data": "<binary>"}]


def test_binary_column_short_string_refs_value_not_misread_as_string():
    """With 2-byte refs the widths coincidentally matched, but the old code
    decoded the binary cell as a string ref; it must stay an int marker."""
    table = _make_icon_table()
    pool = _make_string_pool(["icon.ico"], long_refs=False)
    data = struct.pack("<H", 1) + struct.pack("<H", 1)  # ref 1, marker 1
    rows = table._read_rows(BinaryReader(_FakeStream(data)), pool)
    assert rows == [{"Name": "icon.ico", "Data": "<binary>"}]


def _make_int_table():
    """Two i16 columns (row_size=4); values are stored biased by 0x8000."""
    return Table("TestTable", [Column("A").i16(), Column("B").i16()])


def _bias16(v):
    return (v ^ -0x8000) & 0xFFFF


def test_read_rows_strict_raises_on_bad_length():
    table = _make_int_table()  # row_size = 4
    pool = _make_string_pool([], long_refs=False)
    # 9 bytes: 8 bytes of cell data + 1 trailing byte
    data = struct.pack("<4H", *(_bias16(v) for v in (1, 2, 3, 4))) + b"\x00"
    with pytest.raises(ValueError, match="not a multiple of row size"):
        table._read_rows(BinaryReader(_FakeStream(data)), pool)
