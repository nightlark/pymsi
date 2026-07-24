import io
from types import SimpleNamespace

import pytest

from pymsi import streamname
from pymsi.column import Column
from pymsi.constants import COL_NULLABLE_BIT, COL_STRING_BIT, COL_VALID_BIT
from pymsi.msi.icon import Icon
from pymsi.msi.msi import Msi
from pymsi.msi.shortcut import Shortcut
from pymsi.package import Package
from pymsi.reader import BinaryReader
from pymsi.table import Table


class SizedBytesIO(io.BytesIO):
    @property
    def size(self):
        return len(self.getbuffer())


class FakeStringPool:
    def __init__(self, long_string_refs):
        self.long_string_refs = long_string_refs
        self.calls = 0

    def read_string(self, reader):
        self.calls = 1
        string_ref = reader.read_u16_le()
        if self.long_string_refs:
            string_ref |= reader.read_u8() << 16
        return {1: "qgis.ico"}.get(string_ref)


class FakeOle:
    def __init__(self, streams):
        self.streams = streams

    def exists(self, name):
        return name in self.streams

    def openstream(self, name):
        return io.BytesIO(self.streams[name])


def binary_bits(nullable=False):
    bits = COL_STRING_BIT | COL_VALID_BIT
    if nullable:
        bits |= COL_NULLABLE_BIT
    return bits


def icon_table(nullable=False):
    return Table(
        "Icon",
        [
            Column("Name").string(72).mark_primary_key(),
            Column("Data", binary_bits(nullable)),
        ],
    )


def package_with_streams(streams):
    package = Package.__new__(Package)
    package.ole = FakeOle(streams)
    return package


@pytest.mark.parametrize("nullable", [False, True])
def test_binary_column_is_fixed_width(nullable):
    column = icon_table(nullable).column("Data")

    assert column.type == "binary"
    assert column.width(long_string_refs=False) == 2
    assert column.width(long_string_refs=True) == 2


def test_long_string_ref_icon_row_is_five_bytes():
    pool = FakeStringPool(long_string_refs=True)
    data = SizedBytesIO(b"\x01\x00\x00\x01\x00")

    rows = icon_table()._read_rows(BinaryReader(data), pool)

    assert rows == [{"Name": "qgis.ico", "Data": "<binary>"}]
    assert pool.calls == 1


def test_short_string_ref_does_not_look_up_binary_marker():
    pool = FakeStringPool(long_string_refs=False)
    data = SizedBytesIO(b"\x01\x00\x01\x00")

    rows = icon_table()._read_rows(BinaryReader(data), pool)

    assert rows[0]["Data"] == "<binary>"
    assert pool.calls == 1


def test_genuinely_malformed_row_still_raises():
    pool = FakeStringPool(long_string_refs=True)
    data = SizedBytesIO(b"\x01\x00\x00\x01")

    with pytest.raises(ValueError, match="not a multiple of row size"):
        icon_table()._read_rows(BinaryReader(data), pool)


def test_get_datastream_bytes_returns_bytes_or_none():
    name = streamname.encode_unicode("Icon.qgis.ico", False)
    package = package_with_streams({name: b"icon bytes"})

    assert package.get_datastream_bytes("Icon", "qgis.ico") == b"icon bytes"
    assert package.get_datastream_bytes("Icon", "missing.ico") is None


def test_get_datastream_bytes_validates_stream_identity():
    package = package_with_streams({})

    with pytest.raises(ValueError, match="table name"):
        package.get_datastream_bytes("", "key")
    with pytest.raises(ValueError, match="at least one"):
        package.get_datastream_bytes("Icon")
    with pytest.raises(TypeError, match="strings or integers"):
        package.get_datastream_bytes("Icon", None)


def test_get_row_datastream_bytes_uses_primary_keys_in_column_order():
    table = Table(
        "Binary",
        [
            Column("First").string(32).mark_primary_key(),
            Column("Second").i16().mark_primary_key(),
            Column("Data").binary(),
        ],
    )
    row = {"First": "alpha", "Second": 7, "Data": "<binary>"}
    name = streamname.encode_unicode("Binary.alpha.7", False)
    package = package_with_streams({name: b"payload"})

    assert package.get_row_datastream_bytes(table, row) == b"payload"


def test_get_row_datastream_bytes_validates_table_schema():
    package = package_with_streams({})
    no_binary = Table("Strings", [Column("Name").string(32).mark_primary_key()])
    no_primary_key = Table("Binary", [Column("Data").binary()])

    with pytest.raises(ValueError, match="no binary column"):
        package.get_row_datastream_bytes(no_binary, {"Name": "value"})
    with pytest.raises(ValueError, match="no primary-key columns"):
        package.get_row_datastream_bytes(no_primary_key, {"Data": "<binary>"})


def test_get_row_datastream_bytes_validates_primary_key_values():
    table = Table(
        "Binary",
        [
            Column("Name").string(32).mark_primary_key(),
            Column("Data").binary(),
        ],
    )
    package = package_with_streams({})

    with pytest.raises(TypeError, match="Name"):
        package.get_row_datastream_bytes(table, {"Name": None, "Data": "<binary>"})


def test_icon_data_is_populated_separately_from_its_table_row():
    icon = Icon({"Name": "qgis.ico", "Data": "<binary>"})

    assert icon.data is None
    icon._populate(b"icon bytes")
    assert icon.data == b"icon bytes"


def test_msi_load_icons_reads_and_populates_datastream_bytes():
    table = icon_table()
    row = {"Name": "qgis.ico", "Data": "<binary>"}
    table.rows = [row]

    class FakePackage:
        def get(self, name):
            assert name == "Icon"
            return table

        def get_row_datastream_bytes(self, requested_table, requested_row):
            assert requested_table is table
            assert requested_row is row
            return b"icon bytes"

    msi = Msi.__new__(Msi)
    msi.package = FakePackage()
    msi.icons = {"qgis.ico": Icon(row)}

    msi._load_icons()

    assert msi.icons["qgis.ico"].data == b"icon bytes"


def test_msi_load_icons_rejects_missing_payload_stream():
    table = icon_table()
    row = {"Name": "qgis.ico", "Data": "<binary>"}
    table.rows = [row]

    class FakePackage:
        def get(self, name):
            return table

        def get_row_datastream_bytes(self, requested_table, requested_row):
            return None

    msi = Msi.__new__(Msi)
    msi.package = FakePackage()
    msi.icons = {"qgis.ico": Icon(row)}

    with pytest.raises(ValueError, match="qgis.ico"):
        msi._load_icons()


def test_shortcut_pretty_print_summarizes_loaded_icon_bytes(capsys):
    icon = Icon({"Name": "qgis.ico", "Data": "<binary>"})
    icon._populate(b"\x00\x01\x02")

    shortcut = Shortcut.__new__(Shortcut)
    shortcut.id = "Shortcut"
    shortcut.name = "QGIS"
    shortcut.target = "[#qgis.exe]"
    shortcut.arguments = None
    shortcut.description = None
    shortcut.hotkey = None
    shortcut.icon = icon
    shortcut.icon_index = 0
    shortcut.show_command = 1
    shortcut.working_directory = "INSTALLDIR"
    shortcut.component = SimpleNamespace(
        id="Component", directory=SimpleNamespace(name="INSTALLDIR")
    )
    shortcut.directory = SimpleNamespace(name="INSTALLDIR", id="INSTALLDIR")

    shortcut.pretty_print()

    output = capsys.readouterr().out
    assert "Icon: qgis.ico (3 bytes)" in output
    assert "b'\\x00\\x01\\x02'" not in output
