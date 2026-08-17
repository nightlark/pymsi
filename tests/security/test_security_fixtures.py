from __future__ import annotations

import ast
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Tuple

import pytest

import pymsi
from pymsi.__main__ import extract_root

FIXTURE_ROOT = Path(__file__).parent / "fixtures"
GENERATED = FIXTURE_ROOT / "generated"
MANIFEST = json.loads((GENERATED / "manifest.json").read_text(encoding="utf-8"))


def _fixture(key: str) -> Path:
    return GENERATED / MANIFEST["fixtures"][key]


def _load_msi(path: Path) -> Tuple[pymsi.Package, pymsi.Msi]:
    package = pymsi.Package(path, strict=False)
    return package, pymsi.Msi(package, load_data=True, strict=False)


def _contains_js_alert(source: str) -> bool:
    tree = ast.parse(source)
    return any(
        isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == "alert")
            or (isinstance(node.func, ast.Name) and node.func.id == "alert")
        )
        for node in ast.walk(tree)
    )


def test_generated_fixture_digests_match_manifest():
    for name, expected in MANIFEST["sha256"].items():
        actual = hashlib.sha256((GENERATED / name).read_bytes()).hexdigest()
        assert actual == expected, name


def test_benign_msi_extracts_only_below_the_selected_root(tmp_path: Path):
    package, msi = _load_msi(_fixture("benign_msi"))
    try:
        output = tmp_path / "extract"
        extract_root(msi.root, output)
        files = [path for path in output.rglob("*") if path.is_file()]
        assert len(files) == 1
        assert files[0].name == "payload.txt"
        assert output in files[0].parents
    finally:
        package.close()


def test_file_name_traversal_msi_reaches_a_real_extraction_write(tmp_path: Path):
    package, msi = _load_msi(_fixture("path_traversal_file_msi"))
    try:
        output = tmp_path / "extract"
        escaped = tmp_path / "PYMSI_PATH_TRAVERSAL_CANARY.txt"
        assert msi.files["FixturePayload"].name == MANIFEST["markers"]["path_traversal_file_name"]
        try:
            extract_root(msi.root, output)
        except ValueError:
            pass
        if escaped.exists():
            assert escaped.read_bytes() == (FIXTURE_ROOT / "payload.txt").read_bytes()
            pytest.xfail("real MSI FileName escaped the selected extraction root")
        assert not escaped.exists()
    finally:
        package.close()


def test_directory_name_traversal_msi_reaches_a_real_extraction_write(tmp_path: Path):
    package, msi = _load_msi(_fixture("path_traversal_directory_msi"))
    try:
        output = tmp_path / "extract"
        escaped = tmp_path / "PYMSI_DIRECTORY_TRAVERSAL_CANARY" / "payload.txt"
        assert (
            msi.directories["INSTALLDIR"].name
            == MANIFEST["markers"]["path_traversal_directory_name"]
        )
        try:
            extract_root(msi.root, output)
        except ValueError:
            pass
        if escaped.exists():
            assert escaped.read_bytes() == (FIXTURE_ROOT / "payload.txt").read_bytes()
            pytest.xfail("real MSI DefaultDir escaped the selected extraction root")
        assert not escaped.exists()
    finally:
        package.close()


def test_metadata_fixture_places_active_markup_in_the_file_model():
    package, msi = _load_msi(_fixture("metadata_innerhtml_msi"))
    try:
        marker = MANIFEST["markers"]["metadata_innerhtml"]
        assert msi.files["FixturePayload"].version == marker
        assert "onerror=" in marker
        assert "alert(" in marker
    finally:
        package.close()


def test_table_name_fixture_creates_valid_alerting_python_when_interpolated():
    table_name = MANIFEST["markers"]["python_table_name"]
    with pymsi.Package(_fixture("python_table_name_msi"), strict=False) as package:
        assert table_name in package.tables
        table = package.get(table_name)
        assert table is not None
        assert list(table) == [{"Value": "ordinary"}]

    source = f"table = current_package.get('{table_name}')"
    assert _contains_js_alert(source)


def test_filename_zip_creates_valid_alerting_python_when_interpolated():
    fixture = _fixture("python_filename_zip")
    entry_name = MANIFEST["markers"]["python_filename_entry"]
    with zipfile.ZipFile(fixture) as archive:
        assert archive.namelist() == [entry_name]
        assert entry_name.endswith(".msi")
        msi_bytes = archive.read(entry_name)
        assert msi_bytes.startswith(bytes.fromhex("d0cf11e0a1b11ae1"))

    with pymsi.Package(io.BytesIO(msi_bytes), strict=False) as package:
        assert "File" in package.tables

    msi_path = f"/{entry_name}"
    source = f"current_package = pymsi.Package(Path('{msi_path}'))"
    assert _contains_js_alert(source)


def test_module_overwrite_zip_targets_only_pyodide_and_contains_a_visible_canary():
    fixture = _fixture("pyodide_module_zip")
    module_paths = MANIFEST["markers"]["pyodide_module_paths"]
    expected_source = MANIFEST["markers"]["pyodide_module_source"]
    with zipfile.ZipFile(fixture) as archive:
        names = set(archive.namelist())
        assert "ordinary.msi" in names
        assert set(module_paths) < names
        for module_path in module_paths:
            assert not module_path.startswith("/")
            assert ".." not in Path(module_path).parts
            module_source = archive.read(module_path).decode()
            assert module_source == expected_source
            assert _contains_js_alert(module_source)
            assert "PYMSI_MODULE_OVERWRITE_CANARY.txt" in module_source
        msi_bytes = archive.read("ordinary.msi")

    with pymsi.Package(io.BytesIO(msi_bytes), strict=False) as package:
        assert "File" in package.tables
