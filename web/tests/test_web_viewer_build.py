from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = ROOT / "tools" / "build_web_viewer.py"


def load_builder_module():
    spec = importlib.util.spec_from_file_location("build_web_viewer", BUILD_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_fake_wheel(path: Path, distribution: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{distribution}.dist-info/LICENSE", "Test license\n")
        archive.writestr(f"{distribution}/__init__.py", "")
    return path


def parse_generated_config(path: Path) -> dict:
    source = path.read_text(encoding="utf-8")
    payload = source.split("Object.freeze(", 1)[1].rsplit(");", 1)[0]
    return json.loads(payload)


def test_cdn_build_contains_shared_sources_and_theme_css(tmp_path: Path) -> None:
    output = tmp_path / "dist"
    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--target",
            "cdn",
            "--output-dir",
            str(output),
            "--no-archive",
        ],
        cwd=ROOT,
        check=True,
    )

    distribution = output / "pymsi-viewer-cdn"
    html = (distribution / "index.html").read_text(encoding="utf-8")
    config = (distribution / "assets" / "viewer-config.js").read_text(encoding="utf-8")
    standalone_css = (distribution / "assets" / "standalone.css").read_text(encoding="utf-8")
    shared_js = (distribution / "assets" / "msi_viewer.js").read_text(encoding="utf-8")

    assert '<div id="msi-viewer-app">' in html
    assert "cdn.jsdelivr.net/pyodide/v0.29.1/full/pyodide.js" in html
    assert '"pymsi>=0.0.0rc1"' in config
    assert '"examplesIndexURL": "assets/examples.json"' in config
    assert "prefers-color-scheme: dark" in standalone_css
    assert 'html[data-theme="dark"]' in standalone_css
    assert "readthedocs-flyout" not in shared_js.lower()
    assert (distribution / "assets" / "example.msi").is_file()
    assert (distribution / "SHA256SUMS").is_file()


def test_readthedocs_behavior_is_confined_to_rtd_sources() -> None:
    shared_css = (ROOT / "web" / "viewer" / "msi_viewer.css").read_text(encoding="utf-8")
    shared_js = (ROOT / "web" / "viewer" / "msi_viewer.js").read_text(encoding="utf-8")
    rtd_css = (ROOT / "web" / "viewer" / "rtd.css").read_text(encoding="utf-8")
    rtd_js = (ROOT / "web" / "viewer" / "rtd_integration.js").read_text(encoding="utf-8")

    assert "readthedocs-flyout" not in shared_css.lower()
    assert "readthedocs-flyout" not in shared_js.lower()
    assert "readthedocs-flyout" in rtd_css.lower()
    assert "readthedocs-flyout" in rtd_js.lower()


def test_rtd_build_adds_adapter_without_standalone_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = load_builder_module()
    docs_dir = tmp_path / "docs"
    monkeypatch.setattr(builder, "DOCS_DIR", docs_dir)

    embed_path = builder.build_rtd()
    embed = embed_path.read_text(encoding="utf-8")
    static_dir = docs_dir / "_static" / "msi_viewer"

    assert '<div id="msi-viewer-app">' in embed
    assert "_static/msi_viewer/rtd.css" in embed
    assert "_static/msi_viewer/rtd_integration.js" in embed
    assert "standalone.css" not in embed
    assert "readthedocs-flyout" in (static_dir / "rtd_integration.js").read_text(
        encoding="utf-8"
    ).lower()
    assert "readthedocs-flyout" not in (static_dir / "msi_viewer.js").read_text(
        encoding="utf-8"
    ).lower()


def test_bundled_template_uses_only_local_runtime_sources() -> None:
    builder = load_builder_module()
    html = builder.standalone_html(
        "MSI Viewer and Extractor",
        [
            "assets/vendor/pyodide/pyodide.js",
            "assets/vendor/jszip/jszip.min.js",
            "assets/vendor/sheetjs/xlsx.full.min.js",
            "assets/vendor/sqljs/sql-wasm.min.js",
        ],
    )

    runtime_sources = []
    for line in html.splitlines():
        stripped = line.strip()
        if stripped.startswith("<script "):
            runtime_sources.append(stripped.split('src="', 1)[1].split('"', 1)[0])
        elif stripped.startswith('<link rel="stylesheet"'):
            runtime_sources.append(stripped.split('href="', 1)[1].split('"', 1)[0])

    assert runtime_sources
    assert all(not source.startswith(("http://", "https://", "//")) for source in runtime_sources)


def test_pyodide_package_closure_downloads_dependencies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    builder = load_builder_module()
    pyodide_root = tmp_path / "pyodide"
    pyodide_root.mkdir()
    lock = {
        "packages": {
            "micropip": {
                "depends": ["packaging>=23"],
                "file_name": "micropip.whl",
            },
            "packaging": {
                "depends": [],
                "file_name": "packaging.whl",
            },
        }
    }
    (pyodide_root / "pyodide-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    downloaded = []

    def fake_download(url, destination, offline, expected_sha256=None):
        downloaded.append((url, destination.name, offline, expected_sha256))
        destination.write_bytes(b"wheel")
        return destination

    monkeypatch.setattr(builder, "download_file", fake_download)
    builder.ensure_pyodide_package_closure(pyodide_root, "micropip", offline=False)

    assert {item[1] for item in downloaded} == {"micropip.whl", "packaging.whl"}


def test_bundled_build_assembles_fully_local_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = load_builder_module()
    output_dir = tmp_path / "dist"
    cache_dir = tmp_path / "cache"

    pyodide_root = tmp_path / "fake-pyodide"
    pyodide_root.mkdir()
    for filename in (
        "pyodide.js",
        "pyodide.asm.js",
        "pyodide.asm.wasm",
        "python_stdlib.zip",
        "pyodide-lock.json",
    ):
        (pyodide_root / filename).write_bytes(b"test")

    pymsi_wheel = write_fake_wheel(tmp_path / "pymsi-1.2.3-py3-none-any.whl", "pymsi")
    olefile_wheel = write_fake_wheel(tmp_path / "olefile-0.47-py2.py3-none-any.whl", "olefile")
    downloaded_vendor_assets = []

    def fake_download(url, destination, offline, expected_sha256=None):
        downloaded_vendor_assets.append((url, destination, offline, expected_sha256))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"test vendor asset")
        return destination

    monkeypatch.setattr(builder, "download_file", fake_download)
    monkeypatch.setattr(builder, "ensure_pyodide_core", lambda cache, offline: pyodide_root)
    monkeypatch.setattr(
        builder,
        "build_pymsi_wheel",
        lambda cache, supplied_wheel, offline: pymsi_wheel,
    )
    monkeypatch.setattr(
        builder,
        "download_olefile_wheel",
        lambda cache, offline: olefile_wheel,
    )

    distribution = builder.build_bundled(
        output_dir,
        cache_dir,
        offline=True,
        supplied_wheel=None,
        create_archive=True,
    )

    html = (distribution / "index.html").read_text(encoding="utf-8")
    config = parse_generated_config(distribution / "assets" / "viewer-config.js")
    info = json.loads((distribution / "BUILD-INFO.json").read_text(encoding="utf-8"))

    assert downloaded_vendor_assets
    assert all(item[2] is True for item in downloaded_vendor_assets)
    assert "https://" not in "\n".join(
        line for line in html.splitlines() if "<script" in line or "stylesheet" in line
    )
    assert config["pyodideIndexURL"] == "assets/vendor/pyodide/"
    assert config["sqlJsWasmURL"] == "assets/vendor/sqljs/sql-wasm.wasm"
    assert config["installPackageDependencies"] is False
    assert config["pymsiPackages"] == [
        "assets/python/olefile-0.47-py2.py3-none-any.whl",
        "assets/python/pymsi-1.2.3-py3-none-any.whl",
    ]
    assert info["runtimeNetworkAccess"] is False
    assert (distribution / "assets" / "vendor" / "pyodide" / "pyodide.asm.wasm").is_file()
    assert (distribution / "third-party-licenses").is_dir()
    assert (distribution / "SHA256SUMS").is_file()
    assert (output_dir / "pymsi-viewer-bundled.zip").is_file()

    with zipfile.ZipFile(output_dir / "pymsi-viewer-bundled.zip") as archive:
        names = set(archive.namelist())
    assert "pymsi-viewer-bundled/index.html" in names
    assert "pymsi-viewer-bundled/assets/vendor/pyodide/pyodide.js" in names


def test_source_fingerprint_includes_version_identity_and_ignores_generated_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    builder = load_builder_module()
    root = tmp_path / "source"
    package = root / "src" / "pymsi"
    package.mkdir(parents=True)
    for filename in ("pyproject.toml", "README.md", "LICENSE", "NOTICE"):
        (root / filename).write_text(filename, encoding="utf-8")
    (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(
        builder.subprocess,
        "check_output",
        lambda *args, **kwargs: "v1.0.0",
    )

    first = builder.source_fingerprint()
    (package / "__pycache__").mkdir()
    (package / "__pycache__" / "module.pyc").write_bytes(b"ignored")
    (package / "_version.py").write_text("__version__ = 'generated'\n", encoding="utf-8")
    assert builder.source_fingerprint() == first

    monkeypatch.setattr(
        builder.subprocess,
        "check_output",
        lambda *args, **kwargs: "v1.0.1",
    )
    assert builder.source_fingerprint() != first


def test_offline_wheel_build_requires_cached_or_supplied_wheel(tmp_path: Path) -> None:
    builder = load_builder_module()
    with pytest.raises(RuntimeError, match="Offline build is missing a cached pymsi wheel"):
        builder.build_pymsi_wheel(tmp_path / "cache", supplied_wheel=None, offline=True)


def test_build_info_is_valid_json(tmp_path: Path) -> None:
    builder = load_builder_module()
    destination = tmp_path / "distribution"
    destination.mkdir()
    builder.add_distribution_metadata(
        destination,
        "bundled",
        {"runtimeNetworkAccess": False, "wheels": ["pymsi-test.whl"]},
    )
    info = json.loads((destination / "BUILD-INFO.json").read_text(encoding="utf-8"))
    assert info["variant"] == "bundled"
    assert info["runtimeNetworkAccess"] is False
    assert info["versions"]["pyodide"] == "0.29.1"


@pytest.mark.parametrize(
    "source",
    [
        "msi_viewer.js",
        "msi_analysis.js",
        "msi_binary_viewer.js",
        "rtd_integration.js",
    ],
)
def test_javascript_sources_parse(source: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not installed")
    subprocess.run(
        [node, "--check", str(ROOT / "web" / "viewer" / source)],
        cwd=ROOT,
        check=True,
    )
