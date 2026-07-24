import json

from pymsi.msi.custom_action import (
    collect_custom_actions,
    decode_custom_action_type,
    format_custom_actions,
)


class FakeTable(list):
    pass


class FakePackage:
    def __init__(self, tables=None):
        self.tables = {name: FakeTable(rows) for name, rows in (tables or {}).items()}

    def get(self, name):
        return self.tables.get(name)


def test_exact_type_number_remains_authoritative_over_decomposed_bits():
    action = decode_custom_action_type(39)

    assert action.type_number == 39
    assert action.basic_type == 39
    assert action.primitive_bits == 7
    assert action.source_bits == 0x20
    assert action.kind == "concurrent-install"
    assert action.source_kind == "product-code"
    assert action.name == "Concurrent install of advertised product"


def test_collects_normal_ui_and_control_event_invocations():
    package = FakePackage(
        {
            "CustomAction": [
                {"Action": "Run", "Type": 2, "Source": "Payload", "Target": "--quiet"},
                {"Action": "SetValue", "Type": 51, "Source": "VALUE", "Target": "1"},
            ],
            "InstallExecuteSequence": [
                {"Action": "Run", "Condition": "NOT Installed", "Sequence": 1500},
            ],
            "ControlEvent": [
                {
                    "Dialog_": "WelcomeDlg",
                    "Control_": "Next",
                    "Event": "DoAction",
                    "Argument": "Run",
                    "Condition": "1",
                    "Ordering": 2,
                }
            ],
        }
    )

    collection = collect_custom_actions(package)
    run = collection.by_name["Run"]

    assert run.scheduled
    assert [item.table for item in run.invocations] == [
        "ControlEvent",
        "InstallExecuteSequence",
    ]
    assert run.invocations[0].trigger == "DoAction from WelcomeDlg/Next"
    assert run.invocations[1].condition == "NOT Installed"


def test_advertisement_sequence_references_are_reported_with_validity():
    package = FakePackage(
        {
            "CustomAction": [
                {"Action": "Run", "Type": 2, "Source": "Payload", "Target": ""},
                {"Action": "SetValue", "Type": 51, "Source": "VALUE", "Target": "1"},
            ],
            "AdvtExecuteSequence": [
                {"Action": "Run", "Condition": "1", "Sequence": 10},
                {"Action": "SetValue", "Condition": "1", "Sequence": 20},
            ],
            "AdvtUISequence": [
                {"Action": "SetValue", "Condition": "1", "Sequence": 30},
            ],
        }
    )

    collection = collect_custom_actions(package)
    run = collection.by_name["Run"]
    setter = collection.by_name["SetValue"]

    assert len(run.invalid_invocations) == 1
    assert run.invalid_invocations[0].table == "AdvtExecuteSequence"
    assert "types 19, 35, and 51" in run.invalid_invocations[0].note
    assert [item.allowed for item in setter.invocations] == [True, False]
    assert setter.invocations[1].table == "AdvtUISequence"
    assert collection.to_dict()["summary"]["invalid_invocation_count"] == 2


def test_collection_distinguishes_missing_and_empty_custom_action_tables():
    missing = collect_custom_actions(FakePackage())
    empty = collect_custom_actions(FakePackage({"CustomAction": []}))

    assert not missing.has_custom_action_table
    assert empty.has_custom_action_table
    assert missing.actions == empty.actions == ()
    assert "package has no CustomAction table" in format_custom_actions(missing)
    assert "table is present but empty" in format_custom_actions(empty)


def test_collection_preserves_malformed_rows_and_serializes_cleanly():
    collection = collect_custom_actions(
        FakePackage({"CustomAction": [{"Action": "Broken", "Type": "not-an-int"}]})
    )

    assert len(collection.actions) == 1
    assert collection.actions[0].type_info.kind == "unknown"
    assert any("Could not decode" in warning for warning in collection.warnings)
    assert any(
        "Could not decode Type/ExtendedType" in warning
        for warning in collection.actions[0].type_info.warnings
    )
    json.dumps(collection.to_dict())


def test_patch_uninstall_is_only_read_from_extended_type():
    correct = decode_custom_action_type(2, 0x8000)
    misplaced = decode_custom_action_type(2 | 0x8000)

    assert correct.patch_uninstall
    assert "patch-uninstall only" in correct.capabilities
    assert not misplaced.patch_uninstall
    assert any("belongs in ExtendedType" in warning for warning in misplaced.warnings)
