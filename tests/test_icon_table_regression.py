"""Tests for Table._read_rows size-mismatch error message.

Some MSI files (notably QGIS OSGeo4W installers) contain an Icon table
whose stream data length is not a multiple of the derived row size
(e.g. data_len=5, row_size=6). Prior to this change, Table._read_rows()
raised a generic ``ValueError("Data length is not a multiple of row size")``
with no indication of which table was malformed, making the failure very
hard to diagnose. The error now includes the table name and the actual
data_len / row_size pair so callers can pinpoint the offending table.

Note: this change improves the diagnostic message only; it does not fix
the underlying malformed-table issue itself (see #160 for that).
"""

from pymsi.column import Column
from pymsi.constants import COL_PRIMARY_KEY_BIT, COL_STRING_BIT
from pymsi.reader import BinaryReader
from pymsi.stringpool import StringPool
from pymsi.table import Table


class _FakeOleStream:
    """Minimal OleStream-like object that BinaryReader can consume."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0
        self.size = len(data)

    def read(self, n: int) -> bytes:
        chunk = self._data[self._pos : self._pos + n]
        self._pos += len(chunk)
        return chunk

    def seek(self, pos: int) -> None:
        self._pos = pos

    def tell(self) -> int:
        return self._pos


def _make_icon_table() -> Table:
    # Icon table columns: Name (str, primary key) and Data (str).
    name_col = Column("Name", COL_STRING_BIT | COL_PRIMARY_KEY_BIT)
    name_col.set_bits(COL_STRING_BIT | COL_PRIMARY_KEY_BIT)
    data_col = Column("Data", COL_STRING_BIT)
    data_col.set_bits(COL_STRING_BIT)
    return Table("Icon", [name_col, data_col])


def test_icon_table_size_mismatch_error_includes_table_name() -> None:
    # Reproduce the exact QGIS scenario: 2 str columns => row_size = 6
    # with long_string_refs=True, and a stream with 5 bytes of data.
    table = _make_icon_table()
    reader = BinaryReader(_FakeOleStream(b"\x00" * 5))

    string_pool = StringPool.__new__(StringPool)
    string_pool.long_string_refs = True

    try:
        table._read_rows(reader, string_pool)
    except ValueError as exc:
        message = str(exc)
        assert "Icon" in message, (
            f"error message should identify the failing table, got: {message!r}"
        )
        assert "row size" in message, f"error message should mention the row size, got: {message!r}"
    else:
        raise AssertionError("expected ValueError for malformed Icon table stream")
