from __future__ import annotations

import struct
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from pymsi.__main__ import extract_root, run_suminfo
from pymsi.table import Table
from pymsi.thirdparty.refinery.cab import CabFolder, Cabinet, CabMethod

PAYLOAD = b"codex-security-validation"


class _ResolvedCabFile:
    def __init__(self, data: bytes = PAYLOAD):
        self._data = data

    def decompress(self) -> bytes:
        return self._data


class _ExtractedFile:
    def __init__(self, name: str, data: bytes = PAYLOAD):
        self.name = name
        self.media = object()
        self._resolved = _ResolvedCabFile(data)

    def resolve(self) -> _ResolvedCabFile:
        return self._resolved


def _root_with_file(name: str, data: bytes = PAYLOAD) -> SimpleNamespace:
    file = _ExtractedFile(name, data)
    component = SimpleNamespace(files={"file": file})
    return SimpleNamespace(components={"component": component}, children={})


def _root_with_child(child_name: str) -> SimpleNamespace:
    child = _root_with_file("ordinary.bin")
    child.id = "AttackerDirectory"
    child.name = child_name
    return SimpleNamespace(components={}, children={child.id: child})


def test_benign_extraction_stays_under_output_root(tmp_path: Path):
    output = tmp_path / "extract"
    extract_root(_root_with_file("ordinary.bin"), output)
    assert (output / "ordinary.bin").read_bytes() == PAYLOAD


def test_finding_1_rejects_file_name_that_escapes_extraction_root(tmp_path: Path):
    output = tmp_path / "extract"
    escaped = tmp_path / "escaped.bin"

    try:
        extract_root(_root_with_file("../escaped.bin"), output)
    except ValueError:
        pass

    if escaped.exists():
        assert escaped.read_bytes() == PAYLOAD
        pytest.xfail("finding 1 reproduced: MSI FileName wrote outside the extraction root")
    assert not escaped.exists()


def test_finding_1_rejects_directory_name_that_escapes_extraction_root(tmp_path: Path):
    output = tmp_path / "extract"
    escaped = tmp_path / "escaped-directory" / "ordinary.bin"

    try:
        extract_root(_root_with_child("../escaped-directory"), output)
    except ValueError:
        pass

    if escaped.exists():
        assert escaped.read_bytes() == PAYLOAD
        pytest.xfail("finding 1 reproduced: MSI DefaultDir wrote outside the extraction root")
    assert not escaped.exists()


def test_finding_6_does_not_follow_a_preexisting_output_symlink(tmp_path: Path):
    output = tmp_path / "extract"
    output.mkdir()
    target = tmp_path / "link-target.bin"
    target.write_bytes(b"original")
    link = output / "linked.bin"
    try:
        link.symlink_to(target)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    try:
        extract_root(_root_with_file("linked.bin"), output)
    except ValueError:
        pass

    if target.read_bytes() == PAYLOAD:
        pytest.xfail("finding 6 reproduced: extraction followed and overwrote a symlink target")
    assert target.read_bytes() == b"original"


def _raw_deflate(data: bytes) -> bytes:
    compressor = zlib.compressobj(level=9, wbits=-zlib.MAX_WBITS)
    return compressor.compress(data) + compressor.flush()


def _deflate_folder(data: bytes, declared_size: int) -> CabFolder:
    folder = object.__new__(CabFolder)
    folder.compression = CabMethod.Deflate
    folder.method = (CabMethod.Deflate, 0)
    folder.blocks = [
        SimpleNamespace(data=b"CK" + _raw_deflate(data), decompressed_size=declared_size)
    ]
    folder.decompressed = None
    return folder


def test_benign_cab_deflate_block_matches_its_declared_size():
    data = b"ordinary cab data" * 32
    output = _deflate_folder(data, len(data)).decompress()
    assert bytes(output) == data
    assert len(output) == len(data)


def test_finding_2_rejects_deflate_output_larger_than_declared_size():
    # This is intentionally small enough for routine CI while still proving that the
    # decompressor ignores the CAB block's declared output size.
    expanded = b"A" * (256 * 1024)
    declared_size = 1

    try:
        output = _deflate_folder(expanded, declared_size).decompress()
    except (RuntimeError, ValueError):
        return

    if len(output) > declared_size:
        assert bytes(output) == expanded
        pytest.xfail(
            "finding 2 reproduced: a small Deflate block expanded beyond its declared size"
        )
    assert len(output) <= declared_size


def _cab_header(folder_count: int, folder_table: bytes, block_data: bytes) -> bytes:
    file_offset = 36 + len(folder_table) + len(block_data)
    total_size = file_offset
    header = struct.pack(
        "<4sIIIIIBBHHHHH",
        b"MSCF",
        0,
        total_size,
        0,
        file_offset,
        0,
        3,
        1,
        folder_count,
        0,
        0,
        1,
        0,
    )
    assert len(header) == 36
    return header + folder_table + block_data


def _stored_block(value: bytes = b"A") -> bytes:
    return struct.pack("<IHH", 0, len(value), len(value)) + value


def _cab_with_shared_folder_blocks(folder_count: int, block_count: int) -> bytes:
    data_offset = 36 + (8 * folder_count)
    folder = struct.pack("<IHBB", data_offset, block_count, CabMethod.Nothing, 0)
    folder_table = folder * folder_count
    blocks = b"".join(_stored_block(bytes([65 + index])) for index in range(block_count))
    return _cab_header(folder_count, folder_table, blocks)


def _cab_with_distinct_folder_blocks(folder_count: int) -> bytes:
    data_offset = 36 + (8 * folder_count)
    blocks = [_stored_block(bytes([65 + index])) for index in range(folder_count)]
    offsets = []
    offset = data_offset
    for block in blocks:
        offsets.append(offset)
        offset += len(block)
    folder_table = b"".join(
        struct.pack("<IHBB", start, 1, CabMethod.Nothing, 0) for start in offsets
    )
    return _cab_header(folder_count, folder_table, b"".join(blocks))


def test_benign_distinct_cab_folder_offsets_parse_once_each():
    cabinet = Cabinet(memoryview(_cab_with_distinct_folder_blocks(2)), compute_checksums=False)
    disk = next(iter(cabinet.disks.values()))[0]
    assert len(disk.folders) == 2
    assert [len(folder.blocks) for folder in disk.folders] == [1, 1]


def test_finding_3_rejects_reused_cab_block_offsets_across_folders():
    folder_count = 4
    block_count = 5
    crafted = _cab_with_shared_folder_blocks(folder_count, block_count)

    try:
        cabinet = Cabinet(memoryview(crafted), compute_checksums=False)
    except ValueError:
        return

    disk = next(iter(cabinet.disks.values()))[0]
    parsed_blocks = sum(len(folder.blocks) for folder in disk.folders)
    if parsed_blocks == folder_count * block_count:
        assert len(crafted) < 200
        pytest.xfail("finding 3 reproduced: shared CAB data was reparsed once for every folder")
    assert parsed_blocks <= block_count


class _OneByteColumn:
    name = "value"

    def width(self, long_string_refs: bool) -> int:
        return 1

    def read_value(self, reader: "_CountingReader", string_pool: SimpleNamespace) -> int:
        reader.position += 1
        return 0


class _CountingReader:
    def __init__(self, size: int):
        self.length = size
        self.position = 0

    def size(self) -> int:
        return self.length

    def tell(self) -> int:
        return self.position


def test_benign_table_row_below_the_documented_limit():
    table = Table("OrdinaryTable", [_OneByteColumn()])
    reader = _CountingReader(1)
    string_pool = SimpleNamespace(long_string_refs=False)
    assert table._read_rows(reader, string_pool) == [{"value": 0}]
    assert reader.position == 1


def test_finding_11_rejects_the_first_row_above_the_documented_limit():
    documented_limit = 65_536
    table = Table("AttackerTable", [_OneByteColumn()])
    reader = _CountingReader(documented_limit + 1)
    string_pool = SimpleNamespace(long_string_refs=False)

    try:
        rows = table._read_rows(reader, string_pool)
    except ValueError:
        return

    if len(rows) == documented_limit + 1:
        pytest.xfail(
            "finding 11 reproduced: 65,537 dictionaries were allocated despite the 65,536 message"
        )
    assert len(rows) <= documented_limit


class _Summary:
    def __init__(self, title: str):
        self._title = title

    def title(self) -> str:
        return self._title

    def __getattr__(self, name: str):
        return lambda: None


def test_benign_summary_text_is_printed(capsys: pytest.CaptureFixture[str]):
    run_suminfo(SimpleNamespace(), SimpleNamespace(summary=_Summary("Ordinary title")))
    assert "Title: Ordinary title" in capsys.readouterr().out


def test_finding_9_sanitizes_terminal_control_sequences(
    capsys: pytest.CaptureFixture[str],
):
    osc_title = "\x1b]2;pymsi-security-validation\x07"
    run_suminfo(SimpleNamespace(), SimpleNamespace(summary=_Summary(osc_title)))
    output = capsys.readouterr().out

    if "\x1b" in output or "\x07" in output:
        assert osc_title in output
        pytest.xfail("finding 9 reproduced: raw terminal control bytes reached stdout")
    assert "\x1b" not in output
    assert "\x07" not in output
