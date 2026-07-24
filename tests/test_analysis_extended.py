import base64
import hashlib
import json

import pytest

from pymsi.analysis import (
    DEFAULT_PREVIEW_BYTES,
    analyze_package,
    decode_powershell_command,
    format_analysis,
)


class FakeTable(list):
    pass


class FakePackage:
    def __init__(self, tables=None, streams=None):
        self.tables = {name: FakeTable(rows) for name, rows in (tables or {}).items()}
        self.streams = streams or {}

    def get(self, name):
        return self.tables.get(name)

    def get_datastream_bytes(self, table_name, *primary_keys):
        return self.streams.get((table_name,) + tuple(primary_keys))


def powershell_encoded(text, encoding="utf-16-le"):
    return base64.b64encode(text.encode(encoding)).decode("ascii")


def test_default_preview_is_four_kib_and_terminal_output_is_bounded():
    assert DEFAULT_PREVIEW_BYTES == 4096
    package = FakePackage(
        {"CustomAction": [{"Action": "LargeInlineScript", "Type": 37, "Target": "A" * 5000}]}
    )

    action = analyze_package(package).custom_actions[0]

    assert action.script_preview_truncated
    assert action.script_preview.startswith("A" * 100)
    assert "<904 bytes omitted>" in action.script_preview
    output = format_analysis(analyze_package(package))
    assert len(output) < 7000


def test_encoded_powershell_from_custom_action_data_is_decoded_and_traversed():
    plaintext = "cmd.exe /c whoami"
    encoded = powershell_encoded(plaintext)
    package = FakePackage(
        {
            "Directory": [
                {"Directory": "INSTALLDIR", "Directory_Parent": None, "DefaultDir": "App"}
            ],
            "Component": [
                {"Component": "PayloadComponent", "Directory_": "INSTALLDIR", "KeyPath": "Payload"}
            ],
            "File": [
                {
                    "File": "Payload",
                    "Component_": "PayloadComponent",
                    "FileName": "payload.exe",
                }
            ],
            "CustomAction": [
                {
                    "Action": "SetRunPayload",
                    "Type": 51,
                    "Source": "RunPayload",
                    "Target": f"powershell.exe -NoProfile -EncodedCommand {encoded}",
                },
                {
                    "Action": "RunPayload",
                    "Type": 18 | 0x400,
                    "Source": "Payload",
                    "Target": "",
                },
            ],
            "InstallExecuteSequence": [
                {"Action": "SetRunPayload", "Condition": "1", "Sequence": 100},
                {"Action": "RunPayload", "Condition": "1", "Sequence": 200},
            ],
        }
    )

    action = {item.action: item for item in analyze_package(package).custom_actions}["RunPayload"]

    assert action.decoded_powershell is not None
    assert action.decoded_powershell.origin == "CustomActionData"
    assert action.decoded_powershell.encoding == "utf-16-le"
    assert action.decoded_powershell.text_preview == plaintext
    assert (
        action.decoded_powershell.sha256
        == hashlib.sha256(plaintext.encode("utf-16-le")).hexdigest()
    )
    assert "powershell" in action.launchers
    assert "cmd" in action.launchers
    assert any(item.title == "Encoded PowerShell command" for item in action.findings)


def test_encoded_powershell_ascii_fallback_and_invalid_input_are_explicit():
    ascii_payload = base64.b64encode(b"whoami").decode("ascii")
    decoded = decode_powershell_command(f"pwsh.exe -enc={ascii_payload}", origin="test")
    invalid = decode_powershell_command("powershell.exe -enc %%%", origin="test")

    assert decoded is not None
    assert decoded.text_preview == "whoami"
    assert decoded.encoding in ("utf-8-sig", "utf-8")
    assert decoded.origin == "test"
    assert invalid is not None
    assert invalid.error.startswith("Base64 decode failed")

    metadata_only = decode_powershell_command(
        f"powershell.exe -enc {ascii_payload}", preview_bytes=0
    )
    assert metadata_only is not None
    assert metadata_only.text_preview is None
    assert metadata_only.truncated

    with pytest.raises(ValueError):
        decode_powershell_command("powershell.exe -enc QQ==", preview_bytes=-1)


def test_reglocator_and_appsearch_are_linked_to_custom_action_use():
    package = FakePackage(
        {
            "Property": [
                {"Property": "FOUND_TOOL", "Value": r"C:\Fallback\tool.exe"},
            ],
            "AppSearch": [
                {"Property": "FOUND_TOOL", "Signature_": "ToolRegistryValue"},
            ],
            "RegLocator": [
                {
                    "Signature_": "ToolRegistryValue",
                    "Root": 2,
                    "Key": r"Software\Acme",
                    "Name": "InstallPath",
                    "Type": 0x12,
                }
            ],
            "CustomAction": [
                {
                    "Action": "RunFoundTool",
                    "Type": 50,
                    "Source": "FOUND_TOOL",
                    "Target": "--inspect",
                }
            ],
            "InstallExecuteSequence": [
                {
                    "Action": "RunFoundTool",
                    "Condition": "FOUND_TOOL",
                    "Sequence": 500,
                }
            ],
        }
    )

    analysis = analyze_package(package)
    search = analysis.registry_searches[0]

    assert search.properties == ("FOUND_TOOL",)
    assert search.root == "HKLM"
    assert search.locator_kind == "raw registry value"
    assert search.result_kind == "raw registry value"
    assert search.registry_view == "64-bit"
    assert search.initial_values == (("FOUND_TOOL", r"C:\Fallback\tool.exe"),)
    assert search.referenced_by_custom_actions == ("RunFoundTool",)
    assert any(
        finding.title == "CustomAction references a registry-backed AppSearch result"
        for finding in analysis.findings
    )
    assert "Registry-backed AppSearch facts" in format_analysis(analysis)


def test_signature_table_changes_reglocator_result_to_file_search():
    package = FakePackage(
        {
            "AppSearch": [{"Property": "FOUND_FILE", "Signature_": "FileSig"}],
            "Signature": [{"Signature": "FileSig", "FileName": "tool.exe"}],
            "RegLocator": [
                {
                    "Signature_": "FileSig",
                    "Root": 1,
                    "Key": r"Software\Acme",
                    "Name": "Path",
                    "Type": 2,
                }
            ],
        }
    )

    search = analyze_package(package).registry_searches[0]

    assert search.signature_is_file
    assert search.result_kind == "file matching Signature-table criteria"
    assert any("takes precedence" in warning for warning in search.warnings)


def test_setproperty_destination_is_not_misreported_as_appsearch_dependency():
    package = FakePackage(
        {
            "AppSearch": [{"Property": "MixedCase", "Signature_": "Location"}],
            "RegLocator": [
                {
                    "Signature_": "Location",
                    "Root": 2,
                    "Key": r"Software\Acme",
                    "Name": None,
                    "Type": 0,
                }
            ],
            "CustomAction": [
                {"Action": "OverwriteSearch", "Type": 51, "Source": "MixedCase", "Target": "x"}
            ],
        }
    )

    analysis = analyze_package(package)
    search = analysis.registry_searches[0]

    assert search.referenced_by_custom_actions == ()
    assert any("not a public all-uppercase property" in warning for warning in search.warnings)


def test_servicecontrol_decodes_events_arguments_wait_and_external_services():
    package = FakePackage(
        {
            "Property": [{"Property": "SERVICE_NAME", "Value": "AcmeSvc"}],
            "ServiceInstall": [
                {
                    "ServiceInstall": "InstallAcme",
                    "Name": "[SERVICE_NAME]",
                    "StartType": 2,
                    "Component_": "ServiceComponent",
                }
            ],
            "ServiceControl": [
                {
                    "ServiceControl": "ControlAcme",
                    "Name": "[SERVICE_NAME]",
                    "Event": 0x001 | 0x020 | 0x004,
                    "Arguments": "one[~]two",
                    "Wait": 0,
                    "Component_": "ServiceComponent",
                },
                {
                    "ServiceControl": "ControlExternal",
                    "Name": "ExistingSvc",
                    "Event": 0x008,
                    "Wait": 1,
                    "Component_": "ServiceComponent",
                },
            ],
        }
    )

    analysis = analyze_package(package)
    by_id = {item.identifier: item for item in analysis.service_controls}
    own = by_id["ControlAcme"]
    external = by_id["ControlExternal"]

    assert own.events == ("start during install", "stop during uninstall")
    assert own.start_arguments == ("one", "two")
    assert own.wait_behavior == "wait only until the service reports a pending state"
    assert own.matches_installed_service
    assert any("Reserved install event bit" in warning for warning in own.warnings)
    assert not external.matches_installed_service
    assert external.events == ("delete during install",)
    assert "No matching ServiceInstall row found" in format_analysis(analysis)


def test_registry_persistence_categories_are_precise_and_machine_readable():
    package = FakePackage(
        {
            "Registry": [
                {
                    "Registry": "Ifeo",
                    "Root": 2,
                    "Key": r"Software\Microsoft\Windows NT\CurrentVersion\Image File Execution Options\app.exe",
                    "Name": "Debugger",
                    "Value": "helper.exe",
                },
                {
                    "Registry": "AppInit",
                    "Root": 2,
                    "Key": r"Software\Microsoft\Windows NT\CurrentVersion\Windows",
                    "Name": "AppInit_DLLs",
                    "Value": "helper.dll",
                },
            ]
        }
    )

    analysis = analyze_package(package)
    categories = {
        category for write in analysis.registry_writes for category in write.persistence_categories
    }

    assert "Image File Execution Options debugger" in categories
    assert "AppInit DLL loading" in categories
    serialized = analysis.to_dict()
    encoded = json.dumps(serialized)
    assert '"review_priorities"' in encoded
    assert '"severity"' not in encoded
    assert serialized["summary"]["persistence_finding_count"] == 2
