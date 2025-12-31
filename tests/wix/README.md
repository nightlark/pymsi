# WiX test MSIs for CustomAction coverage

This directory contains a small set of intentionally-minimal MSI installers built with **WiX Toolset v3**.

They exist to exercise different **Windows Installer CustomAction** encodings so tooling (including this repo) can parse/inspect the `CustomAction` table reliably.

## How to build locally

Prereqs:
- Windows
- WiX Toolset v3.11 installed (provides `candle.exe`, `light.exe`, `dark.exe`)

Build all MSIs:

```powershell
cd tests\wix
./build.ps1
```

Output will be under:

- `tests/wix/out/*.msi`

## Test installers

Each MSI is standalone and installs only a trivial text file to `ProgramFilesFolder`.

| MSI | CustomAction(s) exercised | Notes |
|---|---|---|
| `CA1126-Type1126.msi` | `ExeCommand` + `InScript(Deferred)` + `NoImpersonate` | Includes an action whose `CustomAction.Type` is **1126** |
| `CAImmediateProperty.msi` | immediate property-set custom action | Uses `Property`/`Value` style action |
| `CADeferredRollbackCommit.msi` | deferred + rollback + commit custom actions | Demonstrates sequencing variants |
| `CADllEntry.msi` | DLL entrypoint custom action | Uses `BinaryKey` + `DllEntry` |

### The required Type=1126 case

`CA1126-Type1126.msi` includes a custom action `CA_Type1126` that is implemented as an **ExeCommand** custom action scheduled **deferred** and marked **no-impersonate**.

Those flags combine to produce a `CustomAction.Type` value of **1126**.

To verify the Type value:

```powershell
# Decompile and inspect the CustomAction table
$msi = "./out/CA1126-Type1126.msi"
dark.exe $msi -x .\_dark\CA1126
Select-String -Path .\_dark\CA1126\*.wxs -Pattern "CA_Type1126" -Context 0,5
```

Or open the MSI in Orca and check the `CustomAction` table for row `CA_Type1126`.
