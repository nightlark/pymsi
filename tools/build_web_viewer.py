#!/usr/bin/env python3
"""Build standalone and ReadTheDocs variants of the browser MSI viewer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWER_SOURCE = ROOT / "web" / "viewer"
DOCS_DIR = ROOT / "docs"
DEFAULT_OUTPUT_DIR = ROOT / "dist" / "web-viewer"
DEFAULT_CACHE_DIR = ROOT / ".cache" / "web-viewer"

PYODIDE_VERSION = "0.29.1"
JSZIP_VERSION = "3.10.1"
SHEETJS_VERSION = "0.20.2"
SQLJS_VERSION = "1.10.3"
OLEFILE_VERSION = "0.47"
PYMSI_PYPI_REQUIREMENT = "pymsi>=0.0.0rc1"

PYODIDE_CDN_BASE = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
PYODIDE_CORE_URL = (
    "https://github.com/pyodide/pyodide/releases/download/"
    f"{PYODIDE_VERSION}/pyodide-core-{PYODIDE_VERSION}.tar.bz2"
)
PYODIDE_CORE_SHA256 = "75d3896539f9fbe664fb711323949ebd0662cd3e8675c1a880a116d6d6597e74"

OLEFILE_WHEEL_FILENAME = f"olefile-{OLEFILE_VERSION}-py2.py3-none-any.whl"
OLEFILE_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/17/d3/"
    "b64c356a907242d719fc668b71befd73324e47ab46c8ebbbede252c154b2/"
    f"{OLEFILE_WHEEL_FILENAME}"
)
OLEFILE_WHEEL_SHA256 = "543c7da2a7adadf21214938bb79c83ea12b473a4b6ee4ad4bf854e7715e13d1f"

CDN_SCRIPTS = [
    f"{PYODIDE_CDN_BASE}pyodide.js",
    f"https://cdnjs.cloudflare.com/ajax/libs/jszip/{JSZIP_VERSION}/jszip.min.js",
    f"https://cdn.sheetjs.com/xlsx-{SHEETJS_VERSION}/package/dist/xlsx.full.min.js",
    f"https://cdnjs.cloudflare.com/ajax/libs/sql.js/{SQLJS_VERSION}/sql-wasm.min.js",
]

VENDOR_ASSETS = {
    "jszip/jszip.min.js": CDN_SCRIPTS[1],
    "sheetjs/xlsx.full.min.js": CDN_SCRIPTS[2],
    "sqljs/sql-wasm.min.js": CDN_SCRIPTS[3],
    "sqljs/sql-wasm.wasm": (
        f"https://cdnjs.cloudflare.com/ajax/libs/sql.js/{SQLJS_VERSION}/sql-wasm.wasm"
    ),
}

SHARED_FILES = [
    "msi_viewer.css",
    "msi_viewer.js",
    "msi_analysis.js",
    "msi_binary_viewer.js",
]

STANDALONE_INTRODUCTION = """\
<header>
  <h1>MSI Viewer and Extractor</h1>
  <div class="viewer-introduction">
    <p>This interactive tool allows you to view the contents of MSI installer files directly in your browser. The processing happens <strong>entirely on your device</strong> — no files are uploaded to any server.</p>
    <p>Behind the scenes, it is running <a href="https://github.com/nightlark/pymsi/">pymsi</a> using Pyodide.</p>
    <p>Like this tool and want to help out?</p>
    <ul>
      <li>Star the repo to support development: <a href="https://github.com/nightlark/pymsi/">nightlark/pymsi</a></li>
      <li>Found a weird corner case or got feature ideas? <a href="https://github.com/nightlark/pymsi/issues">Open an issue</a>, <a href="https://github.com/nightlark/pymsi/discussions">start a discussion</a>, or <a href="https://github.com/nightlark/pymsi/blob/main/CONTRIBUTING.md">contribute</a>!</li>
      <li>Share this page with coworkers or friends!</li>
    </ul>
  </div>
</header>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=("all", "cdn", "bundled", "rtd"),
        default="all",
        help="Build target (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Standalone output directory (default: {DEFAULT_OUTPUT_DIR.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help=f"Downloaded asset cache (default: {DEFAULT_CACHE_DIR.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Do not access the network; require all bundled inputs in the cache",
    )
    parser.add_argument(
        "--pymsi-wheel",
        type=Path,
        help="Use this pymsi wheel instead of building the current checkout",
    )
    parser.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not create zip archives for standalone targets",
    )
    return parser.parse_args()


def log(message: str) -> None:
    print(f"[web-viewer] {message}", flush=True)


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def ensure_source_files() -> None:
    required = [
        VIEWER_SOURCE / "app.html",
        VIEWER_SOURCE / "standalone.css",
        VIEWER_SOURCE / "rtd.css",
        VIEWER_SOURCE / "rtd_integration.js",
    ]
    required.extend(VIEWER_SOURCE / name for name in SHARED_FILES)
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing viewer source files: {', '.join(missing)}")


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def write_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def viewer_config_script(config: dict) -> str:
    serialized = json.dumps(config, indent=2, sort_keys=True)
    return (
        "// Generated by tools/build_web_viewer.py.\n"
        f"window.PYMSI_VIEWER_CONFIG = Object.freeze({serialized});\n"
    )


def copy_common_assets(destination: Path, include_standalone_css: bool) -> None:
    assets = destination / "assets"
    for filename in SHARED_FILES:
        copy_file(VIEWER_SOURCE / filename, assets / filename)
    if include_standalone_css:
        copy_file(VIEWER_SOURCE / "standalone.css", assets / "standalone.css")

    copy_file(DOCS_DIR / "_static" / "example.msi", assets / "example.msi")
    examples = [
        {
            "filename": "example.msi",
            "name": "Basic Example (example.msi)",
            "url": "assets/example.msi",
        }
    ]
    write_json(assets / "examples.json", examples)


def standalone_html(title: str, vendor_scripts: list[str]) -> str:
    app_markup = (VIEWER_SOURCE / "app.html").read_text(encoding="utf-8").strip()
    scripts = ["assets/viewer-config.js", *vendor_scripts]
    scripts.extend(
        [
            "assets/msi_viewer.js",
            "assets/msi_analysis.js",
            "assets/msi_binary_viewer.js",
        ]
    )
    script_tags = "\n".join(
        f'  <script type="text/javascript" src="{source}"></script>' for source in scripts
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Inspect Windows MSI files locally in your browser with pymsi.">
  <title>{title}</title>
  <link rel="stylesheet" href="assets/standalone.css">
  <link rel="stylesheet" href="assets/msi_viewer.css">
</head>
<body>
<main class="pymsi-viewer-page">
{STANDALONE_INTRODUCTION}
{app_markup}
</main>
{script_tags}
</body>
</html>
"""


def add_distribution_metadata(destination: Path, variant: str, details: dict) -> None:
    copy_file(ROOT / "LICENSE", destination / "LICENSE")
    copy_file(ROOT / "NOTICE", destination / "NOTICE")
    copy_file(ROOT / "web" / "THIRD_PARTY_NOTICES.md", destination / "THIRD_PARTY_NOTICES.md")

    runtime_note = (
        "This variant downloads pinned JavaScript and Pyodide assets from CDNs and installs "
        "pymsi from PyPI when the page starts."
        if variant == "cdn"
        else "This variant contains all runtime assets and does not require network access after it is built."
    )
    readme = f"""pymsi browser MSI viewer ({variant} variant)

{runtime_note}

Serve this directory over HTTP; opening index.html through a file:// URL is not supported.
For example:

    python -m http.server 8000

Then open http://localhost:8000/ in a browser.

The server must return application/wasm for .wasm files.
The page follows the operating system light/dark preference. Set data-theme=light or
data-theme=dark on the html element to force a theme.
"""
    write_text(destination / "README.txt", readme)

    build_info = {
        "format": 1,
        "variant": variant,
        "versions": {
            "jszip": JSZIP_VERSION,
            "olefile": OLEFILE_VERSION,
            "pyodide": PYODIDE_VERSION,
            "sheetjs": SHEETJS_VERSION,
            "sqljs": SQLJS_VERSION,
        },
        **details,
    }
    write_json(destination / "BUILD-INFO.json", build_info)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksums(destination: Path) -> None:
    lines = []
    for path in sorted(destination.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            relative = path.relative_to(destination).as_posix()
            lines.append(f"{sha256_file(path)}  {relative}")
    write_text(destination / "SHA256SUMS", "\n".join(lines) + "\n")


def deterministic_zip(source: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        archive.unlink()

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            relative = Path(source.name) / path.relative_to(source)
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (path.stat().st_mode & 0xFFFF) << 16
            output.writestr(info, path.read_bytes())
    log(f"Created {display_path(archive)}")


def download_file(url: str, destination: Path, offline: bool, expected_sha256: str | None = None) -> Path:
    if destination.is_file():
        if expected_sha256 and sha256_file(destination) != expected_sha256:
            log(f"Discarding cached file with an unexpected checksum: {destination}")
            destination.unlink()
        else:
            return destination

    if offline:
        raise RuntimeError(f"Offline build is missing cached input: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "pymsi-web-viewer-builder/1.0"},
    )
    last_error: Exception | None = None
    for attempt in range(1, 4):
        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            log(f"Downloading {url}")
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open(
                "wb"
            ) as output:
                shutil.copyfileobj(response, output)
            if expected_sha256 and sha256_file(temporary) != expected_sha256:
                raise RuntimeError(f"Checksum mismatch for {url}")
            temporary.replace(destination)
            return destination
        except (OSError, urllib.error.URLError, RuntimeError) as error:
            last_error = error
            temporary.unlink(missing_ok=True)
            if attempt < 3:
                time.sleep(attempt * 2)
    raise RuntimeError(f"Could not download {url}: {last_error}")


def build_cdn(output_dir: Path, create_archive: bool) -> Path:
    destination = output_dir / "pymsi-viewer-cdn"
    reset_directory(destination)
    copy_common_assets(destination, include_standalone_css=True)

    config = {
        "examplesIndexURL": "assets/examples.json",
        "fallbackExamples": [
            {
                "filename": "example.msi",
                "name": "Basic Example (example.msi)",
                "url": "assets/example.msi",
            }
        ],
        "installPackageDependencies": True,
        "pymsiPackages": [PYMSI_PYPI_REQUIREMENT],
        "pyodideIndexURL": PYODIDE_CDN_BASE,
        "sqlJsWasmURL": (
            f"https://cdnjs.cloudflare.com/ajax/libs/sql.js/{SQLJS_VERSION}/sql-wasm.wasm"
        ),
    }
    write_text(destination / "assets" / "viewer-config.js", viewer_config_script(config))
    write_text(destination / "index.html", standalone_html("MSI Viewer and Extractor", CDN_SCRIPTS))
    add_distribution_metadata(
        destination,
        "cdn",
        {"runtimeNetworkAccess": True, "pymsiRequirement": PYMSI_PYPI_REQUIREMENT},
    )
    write_checksums(destination)

    if create_archive:
        deterministic_zip(destination, output_dir / f"{destination.name}.zip")
    log(f"Built CDN variant in {display_path(destination)}")
    return destination


def safe_extract_tar(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with tarfile.open(archive, "r:bz2") as source:
        for member in source.getmembers():
            target = (destination / member.name).resolve()
            if target != destination_resolved and destination_resolved not in target.parents:
                raise RuntimeError(f"Unsafe path in {archive.name}: {member.name}")
        source.extractall(destination)


def find_pyodide_root(extracted: Path) -> Path:
    candidates = sorted(extracted.rglob("pyodide.js"), key=lambda path: len(path.parts))
    if not candidates:
        raise RuntimeError("The Pyodide core archive did not contain pyodide.js")
    root = candidates[0].parent
    if not (root / "pyodide-lock.json").is_file():
        raise RuntimeError("The Pyodide core archive did not contain pyodide-lock.json")
    return root


def canonical_package_name(value: str) -> str:
    value = re.split(r"[<>=!~;\[]", value, maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", value).lower().strip()


def ensure_pyodide_core(cache_dir: Path, offline: bool) -> Path:
    cache_root = cache_dir / f"pyodide-{PYODIDE_VERSION}"
    required_core_files = (
        "pyodide.js",
        "pyodide.asm.js",
        "pyodide.asm.wasm",
        "python_stdlib.zip",
        "pyodide-lock.json",
    )
    if not all((cache_root / filename).is_file() for filename in required_core_files):
        archive = download_file(
            PYODIDE_CORE_URL,
            cache_dir / "downloads" / f"pyodide-core-{PYODIDE_VERSION}.tar.bz2",
            offline,
            PYODIDE_CORE_SHA256,
        )
        with tempfile.TemporaryDirectory(prefix="pymsi-pyodide-") as temporary:
            extracted = Path(temporary)
            safe_extract_tar(archive, extracted)
            source_root = find_pyodide_root(extracted)
            reset_directory(cache_root)
            shutil.copytree(source_root, cache_root, dirs_exist_ok=True)

    ensure_pyodide_package_closure(cache_root, "micropip", offline)
    return cache_root


def ensure_pyodide_package_closure(pyodide_root: Path, root_package: str, offline: bool) -> None:
    lock_path = pyodide_root / "pyodide-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = lock.get("packages", {})
    package_keys = {canonical_package_name(name): name for name in packages}
    root_key = package_keys.get(canonical_package_name(root_package))
    if not root_key:
        raise RuntimeError(f"{root_package!r} was not found in {lock_path}")

    pending = [root_key]
    visited: set[str] = set()
    while pending:
        key = pending.pop()
        canonical_key = canonical_package_name(key)
        if canonical_key in visited:
            continue
        visited.add(canonical_key)
        entry = packages[key]

        filename = entry.get("file_name")
        if filename:
            destination = pyodide_root / filename
            url = PYODIDE_CDN_BASE + urllib.parse.quote(filename, safe="/-_.")
            download_file(url, destination, offline, entry.get("sha256"))

        for dependency in entry.get("depends", []):
            dependency_key = package_keys.get(canonical_package_name(dependency))
            if dependency_key:
                pending.append(dependency_key)


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    paths = [
        ROOT / "pyproject.toml",
        ROOT / "README.md",
        ROOT / "LICENSE",
        ROOT / "NOTICE",
    ]
    paths.extend(sorted((ROOT / "src").rglob("*")))
    for path in paths:
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        if relative == Path("src/pymsi/_version.py"):
            continue
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")

    try:
        version_identity = subprocess.check_output(
            ["git", "-C", str(ROOT), "describe", "--tags", "--always", "--dirty"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        archival = ROOT / ".git_archival.txt"
        version_identity = archival.read_text(encoding="utf-8") if archival.is_file() else "unknown"
    digest.update(b"version-identity\0")
    digest.update(version_identity.encode("utf-8"))
    return digest.hexdigest()[:16]


def build_pymsi_wheel(
    cache_dir: Path,
    supplied_wheel: Path | None,
    offline: bool,
) -> Path:
    if supplied_wheel:
        supplied_wheel = supplied_wheel.resolve()
        if not supplied_wheel.is_file() or supplied_wheel.suffix != ".whl":
            raise RuntimeError(f"Not a wheel file: {supplied_wheel}")
        return supplied_wheel

    wheel_cache = cache_dir / "wheels" / f"pymsi-{source_fingerprint()}"
    existing = sorted(wheel_cache.glob("pymsi-*.whl"))
    if existing:
        return existing[-1]
    if offline:
        raise RuntimeError(
            "Offline build is missing a cached pymsi wheel for this source version. "
            "Build once with network access or pass --pymsi-wheel."
        )

    wheel_cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pymsi-wheel-") as temporary:
        temporary_path = Path(temporary)
        command = [sys.executable, "-m", "build", "--wheel", "--outdir", str(temporary_path)]
        log("Building a pymsi wheel from the current checkout")
        try:
            subprocess.run(command, cwd=ROOT, check=True)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                "Building the bundled viewer requires the project's build dependencies and a "
                "checkout whose version can be resolved. Install `build`, or pass --pymsi-wheel."
            ) from error
        wheels = sorted(temporary_path.glob("pymsi-*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"Expected one pymsi wheel, found {len(wheels)}")
        destination = wheel_cache / wheels[0].name
        shutil.copy2(wheels[0], destination)
        return destination


def download_olefile_wheel(cache_dir: Path, offline: bool) -> Path:
    wheel_dir = cache_dir / "wheels" / f"olefile-{OLEFILE_VERSION}"
    return download_file(
        OLEFILE_WHEEL_URL,
        wheel_dir / OLEFILE_WHEEL_FILENAME,
        offline,
        OLEFILE_WHEEL_SHA256,
    )


def copy_wheel_licenses(wheel: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.namelist():
            basename = Path(member).name
            upper = basename.upper()
            if not basename or not (upper.startswith("LICENSE") or upper.startswith("COPYING")):
                continue
            target = destination / f"{wheel.stem}-{basename}"
            target.write_bytes(archive.read(member))


def copy_tree_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)


def build_bundled(
    output_dir: Path,
    cache_dir: Path,
    offline: bool,
    supplied_wheel: Path | None,
    create_archive: bool,
) -> Path:
    destination = output_dir / "pymsi-viewer-bundled"
    reset_directory(destination)
    copy_common_assets(destination, include_standalone_css=True)

    assets = destination / "assets"
    vendor_root = assets / "vendor"
    for relative, url in VENDOR_ASSETS.items():
        cached = download_file(url, cache_dir / "vendor" / relative, offline)
        copy_file(cached, vendor_root / relative)

    pyodide_root = ensure_pyodide_core(cache_dir, offline)
    copy_tree_contents(pyodide_root, vendor_root / "pyodide")

    pymsi_wheel = build_pymsi_wheel(cache_dir, supplied_wheel, offline)
    olefile_wheel = download_olefile_wheel(cache_dir, offline)
    python_assets = assets / "python"
    bundled_wheels = []
    for wheel in (olefile_wheel, pymsi_wheel):
        target = python_assets / wheel.name
        copy_file(wheel, target)
        bundled_wheels.append(target)
        copy_wheel_licenses(wheel, destination / "third-party-licenses")

    config = {
        "examplesIndexURL": "assets/examples.json",
        "fallbackExamples": [
            {
                "filename": "example.msi",
                "name": "Basic Example (example.msi)",
                "url": "assets/example.msi",
            }
        ],
        "installPackageDependencies": False,
        "pymsiPackages": [f"assets/python/{wheel.name}" for wheel in bundled_wheels],
        "pyodideIndexURL": "assets/vendor/pyodide/",
        "sqlJsWasmURL": "assets/vendor/sqljs/sql-wasm.wasm",
    }
    write_text(assets / "viewer-config.js", viewer_config_script(config))
    local_scripts = [
        "assets/vendor/pyodide/pyodide.js",
        "assets/vendor/jszip/jszip.min.js",
        "assets/vendor/sheetjs/xlsx.full.min.js",
        "assets/vendor/sqljs/sql-wasm.min.js",
    ]
    write_text(destination / "index.html", standalone_html("MSI Viewer and Extractor", local_scripts))
    add_distribution_metadata(
        destination,
        "bundled",
        {
            "runtimeNetworkAccess": False,
            "wheels": [wheel.name for wheel in bundled_wheels],
        },
    )
    write_checksums(destination)

    if create_archive:
        deterministic_zip(destination, output_dir / f"{destination.name}.zip")
    log(f"Built bundled variant in {display_path(destination)}")
    return destination


def build_rtd() -> Path:
    static_dir = DOCS_DIR / "_static" / "msi_viewer"
    generated_dir = DOCS_DIR / "_generated"
    reset_directory(static_dir)
    generated_dir.mkdir(parents=True, exist_ok=True)

    for filename in SHARED_FILES:
        copy_file(VIEWER_SOURCE / filename, static_dir / filename)
    copy_file(VIEWER_SOURCE / "rtd.css", static_dir / "rtd.css")
    copy_file(VIEWER_SOURCE / "rtd_integration.js", static_dir / "rtd_integration.js")

    config = {
        "examplesIndexURL": "_static/examples.json",
        "fallbackExamples": [
            {
                "filename": "example.msi",
                "name": "Basic Example (example.msi)",
                "url": "_static/example.msi",
            }
        ],
        "installPackageDependencies": True,
        "pymsiPackages": [PYMSI_PYPI_REQUIREMENT],
        "pyodideIndexURL": PYODIDE_CDN_BASE,
        "sqlJsWasmURL": (
            f"https://cdnjs.cloudflare.com/ajax/libs/sql.js/{SQLJS_VERSION}/sql-wasm.wasm"
        ),
    }
    write_text(static_dir / "viewer-config.js", viewer_config_script(config))

    app_markup = (VIEWER_SOURCE / "app.html").read_text(encoding="utf-8").strip()
    script_sources = [
        "_static/msi_viewer/viewer-config.js",
        *CDN_SCRIPTS,
        "_static/msi_viewer/msi_viewer.js",
        "_static/msi_viewer/msi_analysis.js",
        "_static/msi_viewer/msi_binary_viewer.js",
        "_static/msi_viewer/rtd_integration.js",
    ]
    scripts = "\n".join(
        f'<script type="text/javascript" src="{source}"></script>' for source in script_sources
    )
    embed = f"""<!-- Generated by tools/build_web_viewer.py; do not edit directly. -->
<link rel="stylesheet" href="_static/msi_viewer/msi_viewer.css">
<link rel="stylesheet" href="_static/msi_viewer/rtd.css">
{app_markup}
{scripts}
"""
    output = generated_dir / "msi_viewer_embed.html"
    write_text(output, embed)
    log(f"Generated ReadTheDocs embed at {display_path(output)}")
    return output


def main() -> int:
    args = parse_args()
    ensure_source_files()
    output_dir = args.output_dir.resolve()
    cache_dir = args.cache_dir.resolve()

    if args.target in ("all", "cdn"):
        build_cdn(output_dir, create_archive=not args.no_archive)
    if args.target in ("all", "bundled"):
        build_bundled(
            output_dir,
            cache_dir,
            offline=args.offline,
            supplied_wheel=args.pymsi_wheel,
            create_archive=not args.no_archive,
        )
    if args.target in ("all", "rtd"):
        build_rtd()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(f"[web-viewer] ERROR: {error}", file=sys.stderr)
        raise SystemExit(1) from error
