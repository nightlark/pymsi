import hashlib
import json

import pytest

from pymsi.analysis import (
    analyze_custom_actions,
    analyze_package,
    decode_custom_action_type,
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


def test_decoder_matches_exact_special_types():
    embedded = decode_custom_action_type(7)
    assert embedded.kind == "concurrent-install"
    assert embedded.source_kind == "substorage"
    assert embedded.source_table is None

    source_tree = decode_custom_action_type(23)
    assert source_tree.kind == "concurrent-install"
    assert source_tree.source_kind == "source-path"
    assert source_tree.source_table is None

    advertised = decode_custom_action_type(39)
    assert advertised.kind == "concurrent-install"
    assert advertised.source_kind == "product-code"
    assert advertised.source_table is None

    assert decode_custom_action_type(19).kind == "error"
    assert decode_custom_action_type(37).name == "Inline JScript"
    assert decode_custom_action_type(38).name == "Inline VBScript"
    assert decode_custom_action_type(53).source_kind == "property"
    assert decode_custom_action_type(54).kind == "vbscript"
    assert decode_custom_action_type(55).kind == "unknown"

    # 1126 (0x466) is deferred inline VBScript with Continue set.
    type_1126 = decode_custom_action_type(1126)
    assert type_1126.basic_type == 38
    assert type_1126.execution == "deferred"
    assert type_1126.return_processing == "synchronous; ignore return code"


def test_decoder_separates_extended_type_and_validates_corner_cases():
    decoded = decode_custom_action_type(3410, 0x8000)
    assert decoded.basic_type == 18
    assert decoded.execution == "rollback"
    assert decoded.kind == "exe"
    assert decoded.source_table == "File"
    assert decoded.patch_uninstall
    assert "no impersonation" in decoded.flags
    assert "patch uninstall only" in decoded.flags
    assert decoded.return_processing == "synchronous; ignore return code"

    wrong_column = decode_custom_action_type(0x8000 | 2)
    assert not wrong_column.patch_uninstall
    assert wrong_column.unknown_type_bits == 0
    assert any("belongs in ExtendedType" in warning for warning in wrong_column.warnings)

    future_bit = decode_custom_action_type(0x10000 | 2)
    assert future_bit.unknown_type_bits == 0x10000

    invalid = decode_custom_action_type(2 | 0x400 | 0x300)
    assert invalid.execution == "invalid in-script scheduling"
    assert any("both set" in warning for warning in invalid.warnings)

    invalid_async = decode_custom_action_type(37 | 0x80)
    assert any("Async is not valid" in warning for warning in invalid_async.warnings)


def test_decoder_reports_options_unsupported_by_specific_basic_types():
    error = decode_custom_action_type(19 | 0x40 | 0x100 | 0x400)
    assert any("does not support return-processing" in item for item in error.warnings)
    assert any("does not support scheduling" in item for item in error.warnings)
    assert any("does not support in-script" in item for item in error.warnings)

    set_directory = decode_custom_action_type(35 | 0x40 | 0x400)
    assert any("does not support return-processing" in item for item in set_directory.warnings)
    assert any("does not support in-script" in item for item in set_directory.warnings)

    set_property = decode_custom_action_type(51 | 0x40 | 0x100)
    assert set_property.execution == "first-sequence"
    assert any("does not support return-processing" in item for item in set_property.warnings)
    assert not any("does not support scheduling" in item for item in set_property.warnings)


def test_powershell_switches_are_only_flagged_when_powershell_is_present():
    package = FakePackage(
        tables={
            "CustomAction": [
                {
                    "Action": "OrdinaryExe",
                    "Type": 34,
                    "Source": "TARGETDIR",
                    "Target": "tool.exe -nop -w hidden -enc U0dWc2JHOD0gV29ybGQ=",
                }
            ]
        }
    )

    action = analyze_custom_actions(package)[0]
    titles = {finding.title for finding in action.findings}
    assert "Encoded PowerShell command" not in titles
    assert "Hidden PowerShell window" not in titles
    assert "PowerShell profile disabled" not in titles


def test_wow6432node_runonceex_registry_key_is_reported():
    package = FakePackage(
        tables={
            "Registry": [
                {
                    "Registry": "DelayedStartup",
                    "Root": 2,
                    "Key": (
                        r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion"
                        r"\RunOnceEx\100"
                    ),
                    "Name": "1",
                    "Value": "payload.exe",
                }
            ]
        }
    )

    analysis = analyze_package(package)
    assert any(finding.title == "Registry Run-key persistence" for finding in analysis.findings)


def test_decoder_accepts_signed_16_bit_values():
    decoded = decode_custom_action_type(-32766, -32768)
    assert decoded.value == 0x8002
    assert decoded.extended_type == 0x8000
    assert decoded.basic_type == 2
    assert decoded.patch_uninstall


def test_decoder_rejects_non_integer_and_out_of_range_values():
    with pytest.raises(ValueError):
        decode_custom_action_type("not-a-number")
    with pytest.raises(ValueError):
        decode_custom_action_type(1 << 40)


def test_exe_commands_follow_source_and_target_semantics():
    package = FakePackage(
        tables={
            "Property": [{"Property": "PowerShellPath", "Value": "[SystemFolder]powershell.exe"}],
            "CustomAction": [
                {"Action": "EmbeddedExe", "Type": 2, "Source": "Payload", "Target": "--quiet"},
                {
                    "Action": "PropertyExe",
                    "Type": 50,
                    "Source": "PowerShellPath",
                    "Target": "-NoProfile -Command whoami",
                },
            ],
        }
    )

    actions = {item.action: item for item in analyze_custom_actions(package)}
    assert actions["EmbeddedExe"].command == "--quiet"
    assert actions["PropertyExe"].command.startswith("[SystemFolder]powershell.exe")
    assert "powershell" in actions["PropertyExe"].launchers


def test_package_analysis_resolves_indirection_scripts_and_persistence():
    script_data = (
        b'var s = new ActiveXObject("WScript.Shell"); '
        b's.Run("powershell.exe -NoProfile -Command whoami");'
    )
    package = FakePackage(
        tables={
            "Property": [
                {"Property": "CompanyName", "Value": "Acme"},
                {
                    "Property": "RunKey",
                    "Value": r"Software\Microsoft\Windows\CurrentVersion\Run",
                },
            ],
            "Directory": [
                {"Directory": "TARGETDIR", "Directory_Parent": None, "DefaultDir": "SourceDir"},
                {
                    "Directory": "INSTALLFOLDER",
                    "Directory_Parent": "TARGETDIR",
                    "DefaultDir": "ACME|[CompanyName]",
                },
                {
                    "Directory": "StartupFolder",
                    "Directory_Parent": "TARGETDIR",
                    "DefaultDir": ".",
                },
                {
                    "Directory": "VendorStartup",
                    "Directory_Parent": "StartupFolder",
                    "DefaultDir": "Acme",
                },
            ],
            "Component": [
                {
                    "Component": "PayloadComponent",
                    "Directory_": "INSTALLFOLDER",
                    "KeyPath": "Payload",
                },
            ],
            "File": [
                {
                    "File": "Payload",
                    "Component_": "PayloadComponent",
                    "FileName": "PAYLOA~1.EXE|payload.exe",
                },
            ],
            "CustomAction": [
                {
                    "Action": "SetRunDropper",
                    "Type": 51,
                    "Source": "RunDropper",
                    "Target": (
                        'powershell.exe -nop -w hidden -enc U0dWc2JHOD0gV29ybGQ= "[#Payload]"'
                    ),
                },
                {
                    "Action": "RunDropper",
                    "Type": 3410,
                    "ExtendedType": 0x8000,
                    "Source": "Payload",
                    "Target": "",
                },
                {
                    "Action": "CheckEnv",
                    "Type": 37,
                    "Source": None,
                    "Target": (
                        'var shell = new ActiveXObject("WScript.Shell"); '
                        'shell.Run("cmd.exe /c whoami");'
                    ),
                },
                {
                    "Action": "BinaryScript",
                    "Type": 5,
                    "Source": "ScriptData",
                    "Target": "Main",
                },
            ],
            "InstallExecuteSequence": [
                {"Action": "CheckEnv", "Condition": "NOT Installed", "Sequence": 100},
                {"Action": "SetRunDropper", "Condition": "NOT Installed", "Sequence": 200},
                {"Action": "RunDropper", "Condition": "NOT Installed", "Sequence": 300},
            ],
            "ControlEvent": [
                {
                    "Dialog_": "WelcomeDlg",
                    "Control_": "Next",
                    "Event": "DoAction",
                    "Argument": "CheckEnv",
                    "Condition": "1",
                    "Ordering": 1,
                },
            ],
            "Registry": [
                {
                    "Registry": "RunPayload",
                    "Root": 2,
                    "Key": "[RunKey]",
                    "Name": "AcmeUpdater",
                    "Value": '"[INSTALLFOLDER]payload.exe" --startup',
                    "Component_": "PayloadComponent",
                },
            ],
            "ServiceInstall": [
                {
                    "ServiceInstall": "PayloadService",
                    "Name": "AcmeSvc",
                    "StartType": 2,
                    "Arguments": "--service [#Payload]",
                    "Component_": "PayloadComponent",
                },
            ],
            "Shortcut": [
                {
                    "Shortcut": "PayloadStartup",
                    "Directory_": "VendorStartup",
                    "Name": "Acme Updater",
                    "Target": "[#Payload]",
                    "Arguments": "--startup",
                },
            ],
        },
        streams={("Binary", "ScriptData"): script_data},
    )

    analysis = analyze_package(package)
    actions = {action.action: action for action in analysis.custom_actions}

    run_dropper = actions["RunDropper"]
    assert run_dropper.type_info.execution == "rollback"
    assert run_dropper.type_info.patch_uninstall
    assert run_dropper.custom_action_data[0].setter_action == "SetRunDropper"
    assert "payload.exe" in run_dropper.custom_action_data[0].resolved_value
    assert "powershell" in run_dropper.launchers
    assert any(finding.title == "Encoded PowerShell command" for finding in run_dropper.findings)
    assert any(finding.title == "Hidden PowerShell window" for finding in run_dropper.findings)
    assert any(finding.category == "indirection" for finding in run_dropper.findings)
    assert any(finding.category == "privilege" for finding in run_dropper.findings)

    check_env = actions["CheckEnv"]
    assert check_env.script_preview.startswith("var shell")
    assert "cmd" in check_env.launchers
    assert check_env.type_info.source_kind == "none"
    assert any(item.table == "ControlEvent" for item in check_env.invocations)
    assert any("WelcomeDlg/Next" in (item.trigger or "") for item in check_env.invocations)

    binary_script = actions["BinaryScript"]
    assert binary_script.data_reference.table == "Binary"
    assert binary_script.data_reference.primary_keys == ("ScriptData",)
    assert binary_script.entrypoint == "Main"
    assert binary_script.binary.size == len(script_data)
    assert binary_script.binary.sha256 == hashlib.sha256(script_data).hexdigest()
    assert binary_script.binary.format == "text"
    assert "powershell" in binary_script.launchers

    package_findings = [finding for finding in analysis.findings if finding.action is None]
    run_key = next(finding for finding in package_findings if "Run-key" in finding.title)
    assert "HKLM" in run_key.detail
    assert r"[INSTALLFOLDER]\payload.exe" in run_key.detail
    assert r"[INSTALLFOLDER]\\payload.exe" not in run_key.detail

    service = next(
        finding for finding in package_findings if finding.title == "Service installation"
    )
    assert "automatic" in service.detail
    assert "binary:" in service.detail
    assert "payload.exe" in service.detail

    shortcut = next(
        finding for finding in package_findings if finding.title == "Startup-folder shortcut"
    )
    assert "payload.exe" in shortcut.detail

    serialized = analysis.to_dict()
    json.dumps(serialized)
    assert serialized["summary"]["custom_action_count"] == 4
    assert "persistence" in serialized["summary"]["categories"]

    output = format_analysis(analysis)
    assert 'CustomAction "RunDropper"' in output
    assert "Deferred action reads CustomActionData" in output
    assert "ExtendedType 32768 (0x8000)" in output
    assert "Registry Run-key persistence" in output


def test_directory_properties_add_one_separator_when_resolved():
    package = FakePackage(
        tables={
            "Directory": [
                {
                    "Directory": "INSTALLFOLDER",
                    "Directory_Parent": "TARGETDIR",
                    "DefaultDir": "Acme",
                }
            ],
            "Registry": [
                {
                    "Registry": "RunWithoutSlash",
                    "Root": 2,
                    "Key": r"Software\Microsoft\Windows\CurrentVersion\Run",
                    "Name": "WithoutSlash",
                    "Value": r"[INSTALLFOLDER]payload.exe",
                },
                {
                    "Registry": "RunWithSlash",
                    "Root": 2,
                    "Key": r"Software\Microsoft\Windows\CurrentVersion\Run",
                    "Name": "WithSlash",
                    "Value": r"[INSTALLFOLDER]\payload.exe",
                },
            ],
        }
    )

    details = [
        finding.detail
        for finding in analyze_package(package).findings
        if finding.title == "Registry Run-key persistence"
    ]
    assert len(details) == 2
    assert all(r"[INSTALLFOLDER]\payload.exe" in detail for detail in details)
    assert all(r"[INSTALLFOLDER]\\payload.exe" not in detail for detail in details)


def test_malformed_type_is_reported_without_stopping_analysis():
    package = FakePackage(
        tables={"CustomAction": [{"Action": "Broken", "Type": "bad", "Target": "value"}]}
    )
    analysis = analyze_package(package)

    assert len(analysis.custom_actions) == 1
    assert any("Could not decode CustomAction 'Broken'" in warning for warning in analysis.warnings)
    assert any(finding.category == "validation" for finding in analysis.custom_actions[0].findings)


def test_script_preview_limit_must_be_non_negative():
    with pytest.raises(ValueError):
        analyze_package(FakePackage(), script_preview_bytes=-1)


def test_service_binary_is_not_guessed_from_an_ambiguous_component():
    package = FakePackage(
        tables={
            "Directory": [
                {
                    "Directory": "INSTALLFOLDER",
                    "Directory_Parent": "TARGETDIR",
                    "DefaultDir": "Acme",
                }
            ],
            "Component": [
                {
                    "Component": "ServiceComponent",
                    "Directory_": "INSTALLFOLDER",
                    "KeyPath": "ServiceRegistryKey",
                }
            ],
            "File": [
                {
                    "File": "ServiceExe",
                    "Component_": "ServiceComponent",
                    "FileName": "service.exe",
                },
                {
                    "File": "HelperDll",
                    "Component_": "ServiceComponent",
                    "FileName": "helper.dll",
                },
            ],
            "ServiceInstall": [
                {
                    "ServiceInstall": "Service",
                    "Name": "AcmeSvc",
                    "StartType": 2,
                    "Component_": "ServiceComponent",
                }
            ],
        }
    )

    service = next(
        finding
        for finding in analyze_package(package).findings
        if finding.title == "Service installation"
    )
    assert "binary:" not in service.detail


def test_package_analysis_finds_task_service_and_startup_persistence():
    package = FakePackage(
        tables={
            "Property": [{"Property": "TaskName", "Value": "Acme Update"}],
            "CustomAction": [
                {
                    "Action": "CreateTask",
                    "Type": 34,
                    "Source": "SystemFolder",
                    "Target": (
                        'schtasks.exe /create /tn "[TaskName]" '
                        '/tr "powershell.exe -NoProfile -Command whoami" /sc onlogon'
                    ),
                },
                {
                    "Action": "CreateService",
                    "Type": 34,
                    "Source": "SystemFolder",
                    "Target": 'sc.exe create AcmeSvc binPath= "C:\\Program Files\\Acme\\svc.exe"',
                },
            ],
            "Shortcut": [
                {
                    "Shortcut": "StartupLink",
                    "Directory_": "StartupFolder",
                    "Name": "Acme",
                    "Target": "[#Payload]",
                    "Arguments": "--startup",
                }
            ],
            "Component": [
                {"Component": "PayloadComponent", "Directory_": "INSTALLFOLDER"},
            ],
            "Directory": [
                {"Directory": "TARGETDIR", "Directory_Parent": None, "DefaultDir": "SourceDir"},
                {
                    "Directory": "INSTALLFOLDER",
                    "Directory_Parent": "TARGETDIR",
                    "DefaultDir": "Acme",
                },
            ],
            "File": [
                {
                    "File": "Payload",
                    "Component_": "PayloadComponent",
                    "FileName": "payload.exe",
                }
            ],
        }
    )

    analysis = analyze_package(package)
    findings = analysis.findings
    assert any(finding.title == "Creates or changes a scheduled task" for finding in findings)
    assert any(finding.title == "Creates or reconfigures a service" for finding in findings)
    startup = next(finding for finding in findings if finding.title == "Startup-folder shortcut")
    assert "payload.exe" in startup.detail


def test_missing_tables_are_not_an_error():
    analysis = analyze_package(FakePackage())
    assert analysis.custom_actions == ()
    assert analysis.findings == ()
    assert "No CustomAction rows found" in format_analysis(analysis)
