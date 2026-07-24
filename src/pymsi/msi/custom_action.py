"""Low-level decoding and collection of Windows Installer custom actions.

This module stays deliberately independent of the higher-level behavior analyzer.
It decodes exact ``CustomAction.Type`` values, preserves the raw row fields, and
records the package locations that can invoke each action.  Security tools can
use these helpers without opting into findings that utilize heuristics.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Any, DefaultDict, Dict, List, Mapping, Optional, Tuple

_TYPE_NUMBER_MASK = 0x003F
_PRIMITIVE_MASK = 0x0007
_SOURCE_BITS_MASK = 0x0030
_RETURN_MASK = 0x00C0
_SCHEDULING_MASK = 0x0300
_IN_SCRIPT = 0x0400
_NO_IMPERSONATE = 0x0800
_SCRIPT_64_BIT = 0x1000
_HIDE_TARGET = 0x2000
_TS_AWARE = 0x4000
_PATCH_UNINSTALL = 0x8000
_KNOWN_TYPE_MASK = 0xFFFF
_KNOWN_EXTENDED_TYPE_MASK = _PATCH_UNINSTALL

# The ordinary install and administrative sequence tables may invoke custom
# actions. Advertisement tables are inspected separately because their rules
# are different and most CustomAction rows are not valid there.
ACTION_SEQUENCE_TABLES = (
    "AdminUISequence",
    "AdminExecuteSequence",
    "InstallUISequence",
    "InstallExecuteSequence",
)
ADVERTISEMENT_SEQUENCE_TABLES = (
    "AdvtUISequence",
    "AdvtExecuteSequence",
)


@dataclass(frozen=True)
class _ActionSpec:
    name: str
    kind: str
    source_kind: str
    source_table: Optional[str]
    target_kind: str
    description: str
    supports_return_processing: bool = True
    supports_scheduling: bool = True
    supports_in_script: bool = True


# Exact values of Type & 0x3f.  The low three and source bits are exposed as
# diagnostic metadata, but are not independently interpreted as the semantic
# source of truth.  Types 7, 23, and 39 are important counterexamples.
ACTION_TYPES: Dict[int, _ActionSpec] = {
    1: _ActionSpec(
        "DLL from Binary",
        "dll",
        "binary",
        "Binary",
        "entrypoint",
        "DLL from Binary table",
    ),
    2: _ActionSpec(
        "EXE from Binary",
        "exe",
        "binary",
        "Binary",
        "arguments",
        "EXE from Binary table",
    ),
    5: _ActionSpec(
        "JScript from Binary",
        "jscript",
        "binary",
        "Binary",
        "function",
        "JScript from Binary table",
    ),
    6: _ActionSpec(
        "VBScript from Binary",
        "vbscript",
        "binary",
        "Binary",
        "function",
        "VBScript from Binary table",
    ),
    7: _ActionSpec(
        "Concurrent install from substorage",
        "concurrent-install",
        "substorage",
        None,
        "property-list",
        "concurrent install from package substorage",
        True,
        True,
        False,
    ),
    17: _ActionSpec(
        "DLL from installed File",
        "dll",
        "file",
        "File",
        "entrypoint",
        "DLL from installed File",
    ),
    18: _ActionSpec(
        "EXE from installed File",
        "exe",
        "file",
        "File",
        "arguments",
        "EXE from installed File",
    ),
    19: _ActionSpec(
        "Error",
        "error",
        "none",
        None,
        "formatted-message",
        "installation error",
        False,
        False,
        False,
    ),
    21: _ActionSpec(
        "JScript from installed File",
        "jscript",
        "file",
        "File",
        "function",
        "JScript from installed File",
    ),
    22: _ActionSpec(
        "VBScript from installed File",
        "vbscript",
        "file",
        "File",
        "function",
        "VBScript from installed File",
    ),
    23: _ActionSpec(
        "Concurrent install from source tree",
        "concurrent-install",
        "source-path",
        None,
        "property-list",
        "concurrent install from source tree",
        True,
        True,
        False,
    ),
    34: _ActionSpec(
        "EXE with directory",
        "exe",
        "directory",
        "Directory",
        "command",
        "EXE command with Directory working directory",
    ),
    35: _ActionSpec(
        "Set directory",
        "set-directory",
        "directory",
        "Directory",
        "formatted-value",
        "Directory assignment",
        False,
        True,
        False,
    ),
    37: _ActionSpec(
        "Inline JScript",
        "jscript",
        "none",
        None,
        "script",
        "inline JScript",
    ),
    38: _ActionSpec(
        "Inline VBScript",
        "vbscript",
        "none",
        None,
        "script",
        "inline VBScript",
    ),
    39: _ActionSpec(
        "Concurrent install of advertised product",
        "concurrent-install",
        "product-code",
        None,
        "property-list",
        "concurrent install of advertised or installed product",
        True,
        True,
        False,
    ),
    50: _ActionSpec(
        "EXE from property",
        "exe",
        "property",
        "Property",
        "arguments",
        "EXE path from Property",
    ),
    51: _ActionSpec(
        "Set property",
        "set-property",
        "property-name",
        "Property",
        "formatted-value",
        "Property assignment",
        False,
        True,
        False,
    ),
    53: _ActionSpec(
        "JScript from property",
        "jscript",
        "property",
        "Property",
        "function",
        "JScript text from Property",
    ),
    54: _ActionSpec(
        "VBScript from property",
        "vbscript",
        "property",
        "Property",
        "function",
        "VBScript text from Property",
    ),
}


@dataclass(frozen=True)
class CustomActionTypeInfo:
    """Decoded ``CustomAction.Type`` and ``ExtendedType`` values."""

    value: int
    extended_type: int
    type_number: int
    primitive_bits: int
    source_bits: int
    name: str
    kind: str
    source_kind: str
    source_table: Optional[str]
    target_kind: str
    execution: str
    return_processing: str
    flags: Tuple[str, ...]
    warnings: Tuple[str, ...]
    unknown_type_bits: int = 0
    unknown_extended_type_bits: int = 0

    @property
    def basic_type(self) -> int:
        """Compatibility alias for the exact six-bit ``type_number``."""

        return self.type_number

    @property
    def in_script(self) -> bool:
        return bool(self.value & _IN_SCRIPT)

    @property
    def hide_target(self) -> bool:
        return bool(self.value & _HIDE_TARGET)

    @property
    def patch_uninstall(self) -> bool:
        return bool(self.extended_type & _PATCH_UNINSTALL)

    @property
    def summary(self) -> str:
        spec = ACTION_TYPES.get(self.type_number)
        description = spec.description if spec else f"unknown type {self.type_number}"
        return f"{self.execution} {description}"

    @property
    def capabilities(self) -> Tuple[str, ...]:
        values: List[str] = []
        if self.kind == "exe":
            values.append("runs executable")
        elif self.kind == "dll":
            values.append("loads DLL")
        elif self.kind in ("jscript", "vbscript"):
            values.append("executes script")
        elif self.kind == "concurrent-install":
            values.append("runs concurrent installation")
        elif self.kind == "set-property":
            values.append("sets property")
        elif self.kind == "set-directory":
            values.append("sets directory")
        elif self.kind == "error":
            values.append("raises installer error")
        if self.execution in ("deferred", "rollback", "commit"):
            values.append(f"{self.execution} execution")
        if "no impersonation" in self.flags:
            values.append("runs without impersonation")
        if self.hide_target:
            values.append("hides target from log")
        if self.return_processing == "asynchronous; do not wait":
            values.append("runs asynchronously without waiting")
        if self.patch_uninstall:
            values.append("patch-uninstall only")
        return tuple(values)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "hex": f"0x{self.value:04x}",
            "extended_type": self.extended_type,
            "extended_type_hex": f"0x{self.extended_type:04x}",
            "type_number": self.type_number,
            # Retained for compatibility with the first draft of this API.
            "basic_type": self.type_number,
            "primitive_bits": self.primitive_bits,
            "source_bits": self.source_bits,
            "name": self.name,
            "kind": self.kind,
            "source_kind": self.source_kind,
            "source_table": self.source_table,
            "target_kind": self.target_kind,
            "execution": self.execution,
            "return_processing": self.return_processing,
            "flags": list(self.flags),
            "warnings": list(self.warnings),
            "unknown_type_bits": self.unknown_type_bits,
            "unknown_extended_type_bits": self.unknown_extended_type_bits,
            "in_script": self.in_script,
            "hide_target": self.hide_target,
            "patch_uninstall": self.patch_uninstall,
            "summary": self.summary,
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class ActionInvocation:
    """A static package location that refers to a custom action."""

    table: str
    condition: Optional[str]
    sequence: Optional[int] = None
    trigger: Optional[str] = None
    allowed: bool = True
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table": self.table,
            "condition": self.condition,
            "sequence": self.sequence,
            "trigger": self.trigger,
            "allowed": self.allowed,
            "note": self.note,
        }


@dataclass(frozen=True)
class CustomActionRecord:
    """A raw CustomAction row plus decoded type and invocation metadata."""

    action: str
    type_info: CustomActionTypeInfo
    source: Optional[str]
    target: Optional[str]
    invocations: Tuple[ActionInvocation, ...] = ()

    @property
    def scheduled(self) -> bool:
        return any(item.allowed for item in self.invocations)

    @property
    def invalid_invocations(self) -> Tuple[ActionInvocation, ...]:
        return tuple(item for item in self.invocations if not item.allowed)

    @property
    def capabilities(self) -> Tuple[str, ...]:
        return self.type_info.capabilities

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "type": self.type_info.to_dict(),
            "source": self.source,
            "target": self.target,
            "invocations": [item.to_dict() for item in self.invocations],
            "scheduled": self.scheduled,
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class CustomActionCollection:
    """Low-level CustomAction table result."""

    actions: Tuple[CustomActionRecord, ...]
    warnings: Tuple[str, ...] = ()
    has_custom_action_table: bool = False

    @property
    def by_name(self) -> Dict[str, CustomActionRecord]:
        return {item.action: item for item in self.actions}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "has_custom_action_table": self.has_custom_action_table,
            "actions": [item.to_dict() for item in self.actions],
            "warnings": list(self.warnings),
            "summary": {
                "custom_action_count": len(self.actions),
                "invoked_action_count": sum(item.scheduled for item in self.actions),
                "unreferenced_action_count": sum(not item.scheduled for item in self.actions),
                "invalid_invocation_count": sum(
                    len(item.invalid_invocations) for item in self.actions
                ),
            },
        }


def _word(value: Any, field_name: str) -> int:
    if value in (None, ""):
        return 0
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer, got {value!r}") from exc
    # MSI two-byte integer columns are signed after decoding. Normalize values
    # such as ExtendedType=-32768 back to their authored 0x8000 bit pattern.
    if -0x8000 <= result < 0:
        result &= 0xFFFF
    if result < 0 or result > 0xFFFFFFFF:
        raise ValueError(f"{field_name} must fit in an unsigned 32-bit integer")
    return result


def decode_custom_action_type(value: Any, extended_type: Any = 0) -> CustomActionTypeInfo:
    """Decode a CustomAction ``Type`` and optional ``ExtendedType`` value.

    ``Type & 0x3f`` is interpreted as an exact action type. Bits ``0x100`` and
    ``0x200`` are scheduling controls for immediate actions, but rollback and
    commit selectors when ``InScript`` is present. ``PatchUninstall`` is read
    from ``ExtendedType``.
    """

    type_value = _word(value, "Type")
    extended_value = _word(extended_type, "ExtendedType")
    type_number = type_value & _TYPE_NUMBER_MASK
    spec = ACTION_TYPES.get(type_number)

    in_script = bool(type_value & _IN_SCRIPT)
    scheduling = type_value & _SCHEDULING_MASK
    warnings: List[str] = []

    if in_script:
        execution = {
            0x000: "deferred",
            0x100: "rollback",
            0x200: "commit",
            0x300: "invalid in-script scheduling",
        }[scheduling]
        if scheduling == 0x300:
            warnings.append(
                "Rollback and commit bits are both set; this in-script combination is undefined."
            )
    else:
        execution = {
            0x000: "immediate",
            0x100: "first-sequence",
            0x200: "once-per-process",
            0x300: "client-repeat",
        }[scheduling]

    return_bits = type_value & _RETURN_MASK
    return_processing = {
        0x000: "synchronous; check return code",
        0x040: "synchronous; ignore return code",
        0x080: "asynchronous; wait at sequence end",
        0x0C0: "asynchronous; do not wait",
    }[return_bits]

    if spec is not None:
        if return_bits and not spec.supports_return_processing:
            warnings.append(f"{spec.name} does not support return-processing options.")
        if scheduling and not spec.supports_scheduling:
            warnings.append(f"{spec.name} does not support scheduling options.")
        if in_script and not spec.supports_in_script:
            warnings.append(f"{spec.name} does not support in-script execution options.")

    flags: List[str] = []
    if in_script:
        flags.append("in-script")
    if type_value & _NO_IMPERSONATE:
        flags.append("no impersonation")
        if not in_script:
            warnings.append("NoImpersonate is only meaningful for in-script custom actions.")
    if type_value & _SCRIPT_64_BIT:
        flags.append("64-bit script")
        if spec is None or spec.kind not in ("jscript", "vbscript"):
            warnings.append("64BitScript is set on a non-script custom action.")
    if type_value & _HIDE_TARGET:
        flags.append("hidden target")
    if type_value & _TS_AWARE:
        flags.append("Terminal Server aware")
        if not in_script:
            warnings.append("TSAware is only meaningful for in-script custom actions.")
        if type_value & _NO_IMPERSONATE:
            warnings.append("TSAware has no effect when NoImpersonate is also set.")
    if extended_value & _PATCH_UNINSTALL:
        flags.append("patch uninstall only")
    if type_value & _PATCH_UNINSTALL:
        warnings.append("0x8000 is set in Type; PatchUninstall belongs in ExtendedType.")

    async_set = bool(type_value & 0x80)
    continue_set = bool(type_value & 0x40)
    if async_set:
        if execution == "rollback":
            warnings.append("Async is not valid for rollback custom actions.")
        if spec is not None and spec.kind in ("jscript", "vbscript"):
            warnings.append("Async is not valid for script custom actions.")
        if spec is not None and spec.kind == "concurrent-install":
            warnings.append("Concurrent installations cannot run asynchronously.")
        if continue_set and (spec is None or spec.kind != "exe"):
            warnings.append("Async+Continue (do not wait) is only valid for EXE custom actions.")

    unknown_type_bits = type_value & ~_KNOWN_TYPE_MASK
    unknown_extended_type_bits = extended_value & ~_KNOWN_EXTENDED_TYPE_MASK
    if unknown_type_bits:
        warnings.append(f"Unknown Type bits are set: 0x{unknown_type_bits:x}.")
    if unknown_extended_type_bits:
        warnings.append(f"Unknown ExtendedType bits are set: 0x{unknown_extended_type_bits:x}.")
    if spec is None:
        warnings.append(f"Unknown custom action type {type_number}.")

    return CustomActionTypeInfo(
        value=type_value,
        extended_type=extended_value,
        type_number=type_number,
        primitive_bits=type_value & _PRIMITIVE_MASK,
        source_bits=type_value & _SOURCE_BITS_MASK,
        name=spec.name if spec else f"Unknown type {type_number}",
        kind=spec.kind if spec else "unknown",
        source_kind=spec.source_kind if spec else "unknown",
        source_table=spec.source_table if spec else None,
        target_kind=spec.target_kind if spec else "unknown",
        execution=execution,
        return_processing=return_processing,
        flags=tuple(flags),
        warnings=tuple(warnings),
        unknown_type_bits=unknown_type_bits,
        unknown_extended_type_bits=unknown_extended_type_bits,
    )


def _table_rows(table: Any) -> List[Mapping[str, Any]]:
    if table is None:
        return []
    iterator = getattr(table, "iter", None)
    if callable(iterator):
        try:
            return list(iterator(True))
        except TypeError:
            pass
    return list(table)


def _rows(
    package: Any, table_name: str, warnings: List[str]
) -> Tuple[bool, List[Mapping[str, Any]]]:
    try:
        table = package.get(table_name)
    except Exception as exc:
        warnings.append(f"Could not read {table_name}: {exc}")
        return False, []
    if table is None:
        return False, []
    try:
        return True, _table_rows(table)
    except Exception as exc:
        warnings.append(f"Could not read {table_name}: {exc}")
        return True, []


def _text(value: Any) -> Optional[str]:
    return None if value is None else str(value)


def _integer(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _advertisement_invocation(
    table_name: str,
    type_info: CustomActionTypeInfo,
    row: Mapping[str, Any],
) -> ActionInvocation:
    if table_name == "AdvtUISequence":
        allowed = False
        note = "AdvtUISequence is unused and should be absent or empty."
    elif type_info.type_number in (19, 35, 51):
        # ICE72 refers to these as the built-in custom-action forms that are
        # permitted in AdvtExecuteSequence.
        allowed = True
        note = "Advertisement sequence permits only custom action types 19, 35, and 51."
    else:
        allowed = False
        note = (
            "Custom actions other than types 19, 35, and 51 are not permitted "
            "in AdvtExecuteSequence."
        )
    return ActionInvocation(
        table=table_name,
        condition=_text(row.get("Condition")),
        sequence=_integer(row.get("Sequence")),
        allowed=allowed,
        note=note,
    )


def collect_custom_actions(package: Any) -> CustomActionCollection:
    """Read and decode CustomAction rows from a Package-like object."""

    warnings: List[str] = []
    has_table, rows = _rows(package, "CustomAction", warnings)
    decoded: List[CustomActionRecord] = []
    names: Dict[str, int] = {}
    for row in rows:
        action_value = row.get("Action")
        if action_value is None:
            warnings.append("CustomAction row has no Action primary key.")
            continue
        action = str(action_value)
        if action in names:
            warnings.append(f"Duplicate CustomAction primary key {action!r}.")
        names[action] = len(decoded)
        try:
            type_info = decode_custom_action_type(row.get("Type"), row.get("ExtendedType", 0))
        except ValueError as exc:
            warnings.append(f"Could not decode CustomAction {action!r}: {exc}")
            # Preserve the row and expose the parsing failure rather than making
            # one malformed action prevent analysis of the rest of the package.
            fallback = decode_custom_action_type(0)
            type_info = replace(
                fallback,
                warnings=fallback.warnings + (f"Could not decode Type/ExtendedType: {exc}",),
            )
        decoded.append(
            CustomActionRecord(
                action=action,
                type_info=type_info,
                source=_text(row.get("Source")),
                target=_text(row.get("Target")),
            )
        )

    invocations: DefaultDict[str, List[ActionInvocation]] = defaultdict(list)
    by_name = {item.action: item for item in decoded}
    for table_name in ACTION_SEQUENCE_TABLES:
        _present, sequence_rows = _rows(package, table_name, warnings)
        for row in sequence_rows:
            action = _text(row.get("Action"))
            if action not in by_name:
                continue
            invocations[action].append(
                ActionInvocation(
                    table=table_name,
                    condition=_text(row.get("Condition")),
                    sequence=_integer(row.get("Sequence")),
                )
            )

    for table_name in ADVERTISEMENT_SEQUENCE_TABLES:
        _present, sequence_rows = _rows(package, table_name, warnings)
        for row in sequence_rows:
            action = _text(row.get("Action"))
            record = by_name.get(action or "")
            if record is None:
                continue
            invocations[record.action].append(
                _advertisement_invocation(table_name, record.type_info, row)
            )

    _present, control_rows = _rows(package, "ControlEvent", warnings)
    for row in control_rows:
        if str(row.get("Event") or "").lower() != "doaction":
            continue
        action = _text(row.get("Argument"))
        if action not in by_name:
            continue
        dialog = row.get("Dialog_")
        control = row.get("Control_")
        trigger = "/".join(str(part) for part in (dialog, control) if part is not None)
        invocations[action].append(
            ActionInvocation(
                table="ControlEvent",
                condition=_text(row.get("Condition")),
                sequence=_integer(row.get("Ordering")),
                trigger=f"DoAction from {trigger}" if trigger else "DoAction",
            )
        )

    result: List[CustomActionRecord] = []
    for item in decoded:
        locations = invocations.get(item.action, [])
        locations.sort(
            key=lambda location: (
                location.table,
                location.sequence if location.sequence is not None else 0,
                location.trigger or "",
            )
        )
        result.append(
            CustomActionRecord(
                action=item.action,
                type_info=item.type_info,
                source=item.source,
                target=item.target,
                invocations=tuple(locations),
            )
        )

    return CustomActionCollection(
        actions=tuple(result),
        warnings=tuple(dict.fromkeys(warnings)),
        has_custom_action_table=has_table,
    )


# Alternate name for integrations that prefer load_* terminology.
load_custom_actions = collect_custom_actions


def format_custom_actions(collection: CustomActionCollection) -> str:
    """Render a faithful, low-level CustomAction table overview."""

    lines = ["MSI CustomAction overview", ""]
    if not collection.has_custom_action_table:
        lines.append("No CustomAction rows found; the package has no CustomAction table.")
    elif not collection.actions:
        lines.append("No CustomAction rows found; the CustomAction table is present but empty.")
    for item in collection.actions:
        type_info = item.type_info
        lines.append(f'CustomAction "{item.action}"')
        lines.append(
            f"  Type {type_info.value} ({type_info.value:#06x}) · "
            f"type number {type_info.type_number} · {type_info.summary}"
        )
        lines.append(f"  Return: {type_info.return_processing}")
        if type_info.flags:
            lines.append(f"  Flags: {', '.join(type_info.flags)}")
        if item.source is not None:
            lines.append(f"  Source: {item.source}")
        if item.target is not None:
            lines.append(f"  Target: {item.target}")
        if item.capabilities:
            lines.append(f"  Capabilities: {', '.join(item.capabilities)}")
        if item.invocations:
            lines.append("  References:")
            for invocation in item.invocations:
                status = "" if invocation.allowed else " [invalid/unreachable]"
                sequence = f" @ {invocation.sequence}" if invocation.sequence is not None else ""
                condition = f" if {invocation.condition}" if invocation.condition else ""
                trigger = f" ({invocation.trigger})" if invocation.trigger else ""
                lines.append(f"    {invocation.table}{sequence}{trigger}{condition}{status}")
                if invocation.note:
                    lines.append(f"      {invocation.note}")
        else:
            lines.append("  References: none found in sequence tables or ControlEvent/DoAction")
        for warning in type_info.warnings:
            lines.append(f"  Warning: {warning}")
        lines.append("")
    if collection.warnings:
        lines.append("Collection warnings")
        lines.extend(f"  - {warning}" for warning in collection.warnings)
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ACTION_SEQUENCE_TABLES",
    "ADVERTISEMENT_SEQUENCE_TABLES",
    "ActionInvocation",
    "CustomActionCollection",
    "CustomActionRecord",
    "CustomActionTypeInfo",
    "collect_custom_actions",
    "decode_custom_action_type",
    "format_custom_actions",
    "load_custom_actions",
]
