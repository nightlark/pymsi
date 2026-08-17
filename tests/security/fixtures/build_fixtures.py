from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent
GENERATED_DIR = FIXTURE_DIR / "generated"
WIX_SOURCE = FIXTURE_DIR / "base_fixture.wxs"

FILE_TRAVERSAL_NAME = "../../../PYMSI_PATH_TRAVERSAL_CANARY.txt"
DIRECTORY_TRAVERSAL_NAME = "../../PYMSI_DIRECTORY_TRAVERSAL_CANARY"
HTML_MARKER = '<img src=x onerror="alert(&apos;PYMSI metadata innerHTML fixture&apos;)">'
TABLE_NAME = "X');__import__('js').alert(7)#"
FILENAME_ENTRY = (
    "trigger') if (__import__('js').alert('PYMSI filename Python injection fixture') "
    "or True) else Path('payload.msi"
)
MODULE_PATHS = (
    "lib/python3.12/site-packages/pymsi/__main__.py",
    "lib/python3.13/site-packages/pymsi/__main__.py",
    "lib/python3.14/site-packages/pymsi/__main__.py",
)
MODULE_SOURCE = (
    "from js import alert\n\n"
    "def extract_root(root, output, is_root=True):\n"
    "    alert('PYMSI Pyodide module overwrite fixture')\n"
    "    output.mkdir(parents=True, exist_ok=True)\n"
    "    (output / 'PYMSI_MODULE_OVERWRITE_CANARY.txt').write_text(\n"
    "        'The ZIP replaced pymsi.__main__ inside the Pyodide filesystem.\\n'\n"
    "    )\n"
).encode()


def _run(*args: str, cwd: Path | None = None) -> None:
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = "1767225600"
    subprocess.run(args, cwd=cwd, env=environment, check=True)


def _copy(source: Path, destination: Path) -> None:
    shutil.copyfile(source, destination)


def _update(msi: Path, query: str) -> None:
    _run("msibuild", str(msi), "-q", query)


def _write_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    for tool in ("wixl", "msibuild"):
        if shutil.which(tool) is None:
            raise SystemExit(f"required fixture builder is unavailable: {tool}")

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pymsi-security-fixtures-") as temp_name:
        temp = Path(temp_name)
        stage = temp / "generated"
        stage.mkdir()
        base = temp / "base.msi"
        _run("wixl", "-o", str(base), str(WIX_SOURCE), cwd=FIXTURE_DIR)

        benign = stage / "benign.msi"
        _copy(base, benign)

        file_traversal = stage / "path_traversal_file.msi"
        _copy(base, file_traversal)
        _update(
            file_traversal,
            f"UPDATE `File` SET `FileName` = '{FILE_TRAVERSAL_NAME}' "
            "WHERE `File` = 'FixturePayload'",
        )

        directory_traversal = stage / "path_traversal_directory.msi"
        _copy(base, directory_traversal)
        _update(
            directory_traversal,
            "UPDATE `Directory` SET `DefaultDir` = "
            f"'{DIRECTORY_TRAVERSAL_NAME}' WHERE `Directory` = 'INSTALLDIR'",
        )

        metadata = stage / "metadata_innerhtml.msi"
        _copy(base, metadata)
        _update(
            metadata,
            f"UPDATE `File` SET `Version` = '{HTML_MARKER}' WHERE `File` = 'FixturePayload'",
        )

        python_table = stage / "python_table_name.msi"
        _copy(base, python_table)
        idt = temp / "python_table.idt"
        idt.write_text(
            f"Value\r\ns72\r\n{TABLE_NAME}\tValue\r\nordinary\r\n",
            encoding="utf-8",
            newline="",
        )
        _run("msibuild", str(python_table), "-i", str(idt))

        base_bytes = base.read_bytes()
        _write_zip(
            stage / "python_filename_injection.zip",
            {FILENAME_ENTRY: base_bytes},
        )
        _write_zip(
            stage / "pyodide_module_overwrite.zip",
            {
                "ordinary.msi": base_bytes,
                **{path: MODULE_SOURCE for path in MODULE_PATHS},
            },
        )

        for hidden_save in GENERATED_DIR.glob(".gsf-save-*"):
            hidden_save.unlink()
        for artifact in stage.iterdir():
            _copy(artifact, GENERATED_DIR / artifact.name)

    artifacts = sorted(
        path
        for path in GENERATED_DIR.iterdir()
        if path.name != "manifest.json" and not path.name.startswith(".")
    )
    manifest = {
        "description": "Inert pymsi security regression fixtures",
        "fixtures": {
            "benign_msi": "benign.msi",
            "path_traversal_file_msi": "path_traversal_file.msi",
            "path_traversal_directory_msi": "path_traversal_directory.msi",
            "metadata_innerhtml_msi": "metadata_innerhtml.msi",
            "python_table_name_msi": "python_table_name.msi",
            "python_filename_zip": "python_filename_injection.zip",
            "pyodide_module_zip": "pyodide_module_overwrite.zip",
        },
        "markers": {
            "path_traversal_file_name": FILE_TRAVERSAL_NAME,
            "path_traversal_directory_name": DIRECTORY_TRAVERSAL_NAME,
            "metadata_innerhtml": HTML_MARKER,
            "python_table_name": TABLE_NAME,
            "python_filename_entry": FILENAME_ENTRY,
            "pyodide_module_paths": list(MODULE_PATHS),
            "pyodide_module_source": MODULE_SOURCE.decode(),
        },
        "sha256": {path.name: _sha256(path) for path in artifacts},
    }
    (GENERATED_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
