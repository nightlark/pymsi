# MSI security regression fixtures

These are deliberately malformed or adversarial **test fixtures**. They contain no installer
custom actions, executable payloads, persistence behavior, network activity, or destructive code.
The only installed file in the base MSI is `payload.txt`.

Generated artifacts live in `generated/`. All visible markers begin with `PYMSI`, and all native
filesystem instructions below keep the write inside a fresh temporary directory.

- `benign.msi` is the negative control.
- `path_traversal_file.msi` changes the MSI `FileName` value to
  `../../../PYMSI_PATH_TRAVERSAL_CANARY.txt`.
- `path_traversal_directory.msi` changes the MSI `DefaultDir` value to
  `../../PYMSI_DIRECTORY_TRAVERSAL_CANARY`.
- `metadata_innerhtml.msi` puts a benign labeled `alert(...)` image error handler in the File
  table's `Version` cell.
- `python_table_name.msi` adds a table whose name displays a labeled dialog if the viewer
  interpolates it into Python. Select the `X');...` table; the numeric dialog value `7` is the
  table-name fixture marker (the MSI table-name limit leaves no room for a longer label).
- `python_filename_injection.zip` stores a valid benign MSI under an injection-shaped filename.
  Loading the ZIP displays a labeled dialog before normal parsing fails.
- `pyodide_module_overwrite.zip` stores a valid benign MSI beside marker modules under Python
  3.12, 3.13, and 3.14 `site-packages/pymsi/__main__.py` paths. Load the ZIP and click **Extract
  All**; a labeled dialog appears and the downloaded archive contains
  `PYMSI_MODULE_OVERWRITE_CANARY.txt`.

## Native path-traversal smoke test

Run each traversal fixture only with a newly created temporary parent:

```console
fixture_root="$(mktemp -d)"
uv run --extra test pymsi extract \
  tests/security/fixtures/generated/path_traversal_file.msi \
  --output "$fixture_root/extract"
find "$fixture_root" -maxdepth 3 -type f -print
```

On the vulnerable revision, the canary appears at
`$fixture_root/PYMSI_PATH_TRAVERSAL_CANARY.txt`, outside `$fixture_root/extract`. Substitute
`path_traversal_directory.msi` to produce
`$fixture_root/PYMSI_DIRECTORY_TRAVERSAL_CANARY/payload.txt`. `benign.msi` is the negative control
and writes only beneath the selected output directory.

## Browser smoke tests

Build or open the MSI Viewer, wait for Pyodide to finish loading, then choose one generated file:

1. `metadata_innerhtml.msi` displays `PYMSI metadata innerHTML fixture` while rendering the Files
   tab on a vulnerable deployment.
2. `python_table_name.msi` loads normally; select the `X');...` table to display the table-name
   Python-injection marker `7`.
3. `python_filename_injection.zip` displays the filename Python-injection marker during loading.
   An error after the dialog is expected because the proof deliberately redirects parsing to a
   nonexistent inert path.
4. `pyodide_module_overwrite.zip` loads `ordinary.msi`; click **Extract All** to display the module
   overwrite marker and download the canary.

A Content Security Policy that blocks inline event handlers may suppress the metadata dialog even
while the unsafe `innerHTML` sink remains. The Node regression test verifies the sink directly.

Rebuild with the `wixl` and `msibuild` commands from msitools installed:

```console
python3 tests/security/fixtures/build_fixtures.py
```

The generated `manifest.json` records exact marker values and SHA-256 digests. MSI bytes can vary
between rebuilds because msitools updates summary timestamps and revision metadata; the manifest
is regenerated with them. Regression tests keep all filesystem effects inside pytest temporary
directories and never install these MSIs.
