# Custom action and installer analysis

`pymsi` can decode Windows Installer `CustomAction` rows and produce a lightweight
static summary of installer capabilities and package facts. The report assigns review
priorities to help an analyst decide where to look first. A review priority is not a
malware verdict: services, scripts, elevated custom actions, registry searches, and the
other surfaced behaviors all have legitimate installer uses.

## Command line

Use `customactions` (or its `ca` alias) for a faithful low-level view of the table and
its static invocation sites:

```console
pymsi customactions installer.msi
pymsi ca installer.msi --json
```

Use `analyze` for cross-table resolution and capability or behavior-oriented findings:

```console
pymsi analyze installer.msi
pymsi analyze installer.msi --json
pymsi analyze installer.msi --script-preview-bytes 8192
```

Script and decoded PowerShell previews are limited to 4096 bytes by default. Set
`--script-preview-bytes 0` when only metadata and hashes are needed. Binary payload
hashes and sizes still describe the complete stream; analysis results retain a reference
to the payload rather than embedding all of its bytes.

## Python API

The low-level layer performs exact type decoding and collects package references without
assigning security meaning:

```python
import pymsi

collection = pymsi.collect_custom_actions(package)
for action in collection.actions:
    print(action.action, action.type_info.type_number, action.type_info.summary)
    for invocation in action.invocations:
        print(" ", invocation.table, invocation.condition, invocation.allowed)

machine_readable = collection.to_dict()
```

Useful low-level helpers are:

```python
pymsi.decode_custom_action_type(type_value, extended_type=0)
pymsi.collect_custom_actions(package)
pymsi.load_custom_actions(package)  # alias
pymsi.format_custom_actions(collection)
```

The analysis layer resolves common references and produces package-level facts:

```python
analysis = pymsi.analyze_package(package)

for action in analysis.custom_actions:
    print(action.action, action.type_info.summary)
    if action.command:
        print("  command:", action.command)
    for finding in action.findings:
        print(
            f"  [{finding.review_priority} review] "
            f"{finding.title}: {finding.detail}"
        )

for search in analysis.registry_searches:
    print(search.properties, search.root, search.key, search.result_kind)

for control in analysis.service_controls:
    print(control.resolved_name, control.events)

machine_readable = analysis.to_dict()
```

`analyze_custom_actions(package)` returns only interpreted custom actions.
`analyze_installer(package)` is an alias for `analyze_package(package)`.

The helpers accept a Package-like object with `get(table_name)`. Reading and hashing a
Binary-table payload additionally uses
`get_datastream_bytes(table_name, *primary_keys)`, which keeps the API suitable for
sandbox and inspection-tool integrations without depending on the CLI.

## What is surfaced

The analysis currently reports:

- JScript and VBScript actions, including inline, Binary-table, installed-file, and
  Property-backed sources, optional function names, and bounded previews when bytes are
  available.
- EXE and DLL actions, including resolved Property/File/Directory sources and DLL entry
  points.
- Commands that reference PowerShell, `cmd`, `rundll32`, `regsvr32`, `mshta`,
  `schtasks`, `sc`, and other commonly useful launchers.
- PowerShell `EncodedCommand` arguments, decoded only after the effective command has
  been identified as PowerShell or `pwsh`. The decoded size and SHA-256 cover the full
  byte string while the retained plaintext is bounded.
- Deferred, rollback, and commit actions that can read `CustomActionData`, including all
  simple type 51 setters and matching initial Property-table values. Setter conditions
  and sequence locations are preserved instead of selecting one possible runtime value.
- Registry writes, with focused persistence categories for Run/RunOnce, Winlogon,
  Image File Execution Options, Active Setup, AppInit/AppCert DLL loading, shell service
  objects, and service ImagePath values.
- `ServiceInstall`, `ServiceControl`, Startup-folder shortcuts, and command-based service
  or scheduled-task creation.
- Registry-backed AppSearch facts by joining `AppSearch`, `RegLocator`, and `Signature`.
  The report records the registry view, authored locator type, resulting search kind,
  initial fallback property values, and custom actions that reference the property.
- Hidden targets, no-impersonation execution, asynchronous no-wait execution, nested
  installs, unknown types, malformed flags, and invalid or unreachable sequence-table
  references.

Property, File, Component, and Directory references are expanded when they can be
resolved without simulating Windows Installer. Conditions are retained but not evaluated.
AppSearch results are described as values that *can* populate a property because the
actual result depends on the target system and the AppSearch locator order.

## Type-decoding notes

`type_number` is the exact value of `CustomAction.Type & 0x3f` and is the semantic source
of truth. `primitive_bits` and `source_bits` are also exposed for diagnostics, but they
must not be interpreted independently for special exact values. In particular, types 7,
23, and 39 have distinct concurrent-install source semantics.

The `0x100` and `0x200` bits are context-dependent. Without `InScript` (`0x400`) they are
multiple-execution scheduling options; with `InScript` they select rollback or commit
execution. `PatchUninstall` (`0x8000`) is read from the `ExtendedType` column rather than
from `Type`.

The four install and administrative sequence tables are ordinary custom-action invocation
sites. Advertisement tables are inspected separately: `AdvtUISequence` is treated as
unused, and only action types 19, 35, and 51 are accepted in `AdvtExecuteSequence`.
`ControlEvent` rows whose event is `DoAction` are also collected.

## Limits

The analyzer does not execute custom actions, evaluate MSI conditions, emulate property
changes, inspect every extracted installed file, or fully expand every formatted-string
construct. An unresolved reason is retained when a source or payload cannot be inspected.
Use the table, stream, and file views for accessing the underlying evidence.
