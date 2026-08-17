# Security validation tests

These tests and their real MSI/ZIP fixtures reproduce the security properties reported by the Codex Security scan of commit
`66931a12d992d2ffefc92b9958b783f1f45248db`. They modify no production code and use only
temporary files, small in-memory inputs, and stubbed browser APIs.

The tests express the desired secure behavior. When the current revision demonstrably violates
that behavior, pytest records an `XFAIL` and Node records a `TODO` after first checking the exact
unsafe effect. A fixed implementation should make the same test pass normally.

## Validation rubric

Each finding is evaluated against the same five criteria:

1. **Source:** attacker-controlled MSI, CAB, ZIP, filename, table, or metadata input reaches the
   documented CLI/library/viewer interface.
2. **Control:** the closest path, size, escaping, quoting, or terminal-safety control is absent or
   can be bypassed.
3. **Sink:** the test observes the precise file write, parser work, decompressed output, generated
   Python, HTML, exported CSV, or terminal bytes.
4. **Negative control:** a nearby benign value is accepted without creating the security effect
   where a bounded negative control is practical.
5. **Safety:** all effects remain inside pytest temporary directories or in-memory fakes, and all
   resource tests use deliberately small inputs.

| Scan finding | Test coverage | Expected at scanned revision |
| --- | --- | --- |
| 1. MSI names escape extraction root | `test_native_security.py`, fixture tests | Unit XFAILs plus end-to-end XFAILs from valid FileName and DefaultDir MSIs |
| 2. CAB decompression lacks budgets | `test_native_security.py` | XFAIL after bounded compressed input exceeds its declared size |
| 3. CAB counts multiply parser work | `test_native_security.py` | XFAIL after shared block offsets are parsed once per folder |
| 4. MSI metadata reaches `innerHTML` | MSI fixture plus `test_msi_viewer_security.mjs` | Parsed MSI metadata reaches the raw-markup sink and records TODO |
| 5. Names become executable Python | MSI/ZIP fixtures plus `test_msi_viewer_security.mjs` | Python AST parsing finds valid fixture-derived alert calls at the filename and table sinks |
| 6. Extraction follows links | `test_native_security.py` | XFAIL after a symlink target inside the temp area is overwritten |
| 7. CSV formulas remain active | `test_msi_viewer_security.mjs` | TODO after exported CSV begins a cell with `=` |
| 8. ZIP paths overwrite Pyodide modules | ZIP fixture plus `test_msi_viewer_security.mjs` | TODO after a benign alerting module is written under `site-packages` |
| 9. CLI output preserves terminal controls | `test_native_security.py` | XFAIL after raw ESC/OSC bytes reach captured stdout |
| 10. ZIP expansion precedes size warning | `test_msi_viewer_security.mjs` | TODO after a declared oversized entry is inflated |
| 11. Table guard permits 65,537 rows | `test_native_security.py` | XFAIL after 65,537 row dictionaries are allocated |

## Run

From the repository root:

```console
pytest -q -rx tests/security/test_native_security.py
pytest -q -rx tests/security/test_security_fixtures.py
node --test tests/security/test_msi_viewer_security.mjs
```

The CAB decompression case expands only 256 KiB, the table case stops at 65,537 one-byte rows,
and the ZIP-bomb case uses a fake entry that returns one byte. The real MSI/ZIP fixtures contain
only canary text and labeled browser dialogs; automated tests parse their Python/HTML markers but
do not execute them.
