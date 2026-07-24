"""Static MSI behavior analysis built on the low-level CustomAction decoder.

The analyzer reports capabilities, package facts, and items that may deserve
review.  A review priority is triage guidance only; it is not a malware verdict.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import (
    Any,
    DefaultDict,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Set,
    Tuple,
)

from .msi.custom_action import (
    ActionInvocation,
    CustomActionCollection,
    CustomActionRecord,
    CustomActionTypeInfo,
    collect_custom_actions,
    decode_custom_action_type,
    format_custom_actions,
    load_custom_actions,
)

DEFAULT_PREVIEW_BYTES = 4096

_PROPERTY_TOKEN = re.compile(r"\[([^\]]+)\]")
_RUN_KEY_PATH = re.compile(
    r"(?i)(?:^|\\)software\\(?:wow6432node\\)?microsoft\\windows\\currentversion\\"
    r"(?:run|runonce|runonceex|runservices|runservicesonce|policies\\explorer\\run)(?:\\|$)"
)

_LAUNCHERS = (
    (
        "powershell",
        re.compile(r"(?i)(?:^|[\\/\s\"'\]])powershell(?:\.exe)?(?:[\s\"']|$)"),
    ),
    ("pwsh", re.compile(r"(?i)(?:^|[\\/\s\"'\]])pwsh(?:\.exe)?(?:[\s\"']|$)")),
    ("cmd", re.compile(r"(?i)(?:^|[\\/\s\"'\]])cmd(?:\.exe)?(?:[\s\"']|$)")),
    (
        "rundll32",
        re.compile(r"(?i)(?:^|[\\/\s\"'\]])rundll32(?:\.exe)?(?:[\s\"']|$)"),
    ),
    (
        "regsvr32",
        re.compile(r"(?i)(?:^|[\\/\s\"'\]])regsvr32(?:\.exe)?(?:[\s\"']|$)"),
    ),
    ("mshta", re.compile(r"(?i)(?:^|[\\/\s\"'\]])mshta(?:\.exe)?(?:[\s\"']|$)")),
    (
        "wscript",
        re.compile(r"(?i)(?:^|[\\/\s\"'\]])wscript(?:\.exe)?(?:[\s\"']|$)"),
    ),
    (
        "cscript",
        re.compile(r"(?i)(?:^|[\\/\s\"'\]])cscript(?:\.exe)?(?:[\s\"']|$)"),
    ),
    (
        "certutil",
        re.compile(r"(?i)(?:^|[\\/\s\"'\]])certutil(?:\.exe)?(?:[\s\"']|$)"),
    ),
    (
        "bitsadmin",
        re.compile(r"(?i)(?:^|[\\/\s\"'\]])bitsadmin(?:\.exe)?(?:[\s\"']|$)"),
    ),
    (
        "schtasks",
        re.compile(r"(?i)(?:^|[\\/\s\"'\]])schtasks(?:\.exe)?(?:[\s\"']|$)"),
    ),
    (
        "sc",
        re.compile(r"(?i)(?:^|[\\/\s\"'\]])sc(?:\.exe)?\s+(?:create|config)\b"),
    ),
    (
        "msiexec",
        re.compile(r"(?i)(?:^|[\\/\s\"'\]])msiexec(?:\.exe)?(?:[\s\"']|$)"),
    ),
    ("wmic", re.compile(r"(?i)(?:^|[\\/\s\"'\]])wmic(?:\.exe)?(?:[\s\"']|$)")),
    (
        "installutil",
        re.compile(r"(?i)(?:^|[\\/\s\"'\]])installutil(?:\.exe)?(?:[\s\"']|$)"),
    ),
)

_POWERSHELL_ENCODED_ARGUMENT = re.compile(
    r"(?ix)(?:^|\s)[-/]"
    r"(?:e|ec|enc|enco|encod|encode|encoded|encodedc|encodedco|encodedcom|"
    r"encodedcomma|encodedcomman|encodedcommand)"
    r"(?:\s+|[:=])"
    r"(?:\"([^\"]+)\"|'([^']+)'|([^\s\"']+))"
)

_ROOT_NAMES = {-1: "HKCU-or-HKLM", 0: "HKCR", 1: "HKCU", 2: "HKLM", 3: "HKU"}
_REGLOCATOR_ROOT_NAMES = {0: "HKCR", 1: "HKCU", 2: "HKLM", 3: "HKU"}


@dataclass(frozen=True)
class DataReference:
    """Reference to a payload stored by an MSI OBJECT column."""

    table: str
    primary_keys: Tuple[Any, ...]
    label: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table": self.table,
            "primary_keys": list(self.primary_keys),
            "label": self.label,
        }


@dataclass(frozen=True)
class BinaryPayloadInfo:
    """Metadata for a referenced Binary-table payload."""

    reference: DataReference
    size: int
    sha256: str
    format: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reference": self.reference.to_dict(),
            "size": self.size,
            "sha256": self.sha256,
            "format": self.format,
        }


@dataclass(frozen=True)
class DecodedPowerShellCommand:
    """Bounded decode of a PowerShell EncodedCommand argument."""

    origin: Optional[str]
    encoded_argument_length: int
    decoded_size: Optional[int]
    sha256: Optional[str]
    encoding: Optional[str]
    text_preview: Optional[str]
    truncated: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin": self.origin,
            "encoded_argument_length": self.encoded_argument_length,
            "decoded_size": self.decoded_size,
            "sha256": self.sha256,
            "encoding": self.encoding,
            "text_preview": self.text_preview,
            "truncated": self.truncated,
            "error": self.error,
        }


@dataclass(frozen=True)
class PropertyAssignment:
    """A possible source for a deferred action's CustomActionData."""

    property_name: str
    value: str
    resolved_value: str
    setter_action: Optional[str] = None
    invocations: Tuple[ActionInvocation, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "property": self.property_name,
            "value": self.value,
            "resolved_value": self.resolved_value,
            "setter_action": self.setter_action,
            "invocations": [item.to_dict() for item in self.invocations],
        }


@dataclass(frozen=True)
class AnalysisFinding:
    """A capability or fact assigned a review priority for triage."""

    category: str
    review_priority: str
    title: str
    detail: str
    action: Optional[str] = None
    table: Optional[str] = None
    reference: Optional[DataReference] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "review_priority": self.review_priority,
            "title": self.title,
            "detail": self.detail,
            "action": self.action,
            "table": self.table,
            "reference": self.reference.to_dict() if self.reference else None,
        }


@dataclass(frozen=True)
class RegistryWriteInfo:
    """A Registry-table write, whether or not it resembles persistence."""

    root: str
    key: str
    name: Optional[str]
    value: Optional[str]
    resolved_value: Optional[str]
    component: Optional[str]
    persistence_categories: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root": self.root,
            "key": self.key,
            "name": self.name,
            "value": self.value,
            "resolved_value": self.resolved_value,
            "component": self.component,
            "persistence_categories": list(self.persistence_categories),
        }


@dataclass(frozen=True)
class RegistrySearchInfo:
    """A RegLocator search and the AppSearch properties it can populate."""

    signature: str
    properties: Tuple[str, ...]
    root: str
    key: str
    name: Optional[str]
    resolved_name: Optional[str]
    locator_type: int
    locator_kind: str
    result_kind: str
    registry_view: str
    signature_is_file: bool
    initial_values: Tuple[Tuple[str, str], ...] = ()
    referenced_by_custom_actions: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signature": self.signature,
            "properties": list(self.properties),
            "root": self.root,
            "key": self.key,
            "name": self.name,
            "resolved_name": self.resolved_name,
            "locator_type": self.locator_type,
            "locator_kind": self.locator_kind,
            "result_kind": self.result_kind,
            "registry_view": self.registry_view,
            "signature_is_file": self.signature_is_file,
            "initial_values": [
                {"property": name, "value": value} for name, value in self.initial_values
            ],
            "referenced_by_custom_actions": list(self.referenced_by_custom_actions),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class ServiceControlInfo:
    """Decoded ServiceControl row."""

    identifier: str
    name: str
    resolved_name: str
    event_value: int
    events: Tuple[str, ...]
    arguments: Optional[str]
    resolved_arguments: Optional[str]
    start_arguments: Tuple[str, ...]
    wait: Optional[int]
    wait_behavior: str
    component: Optional[str]
    matches_installed_service: bool
    warnings: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identifier": self.identifier,
            "name": self.name,
            "resolved_name": self.resolved_name,
            "event_value": self.event_value,
            "events": list(self.events),
            "arguments": self.arguments,
            "resolved_arguments": self.resolved_arguments,
            "start_arguments": list(self.start_arguments),
            "wait": self.wait,
            "wait_behavior": self.wait_behavior,
            "component": self.component,
            "matches_installed_service": self.matches_installed_service,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class CustomActionInfo:
    """Interpreted CustomAction row with some cross-table resolution."""

    action: str
    type_info: CustomActionTypeInfo
    source: Optional[str]
    target: Optional[str]
    resolved_source: Optional[str]
    resolved_target: Optional[str]
    source_origin: str
    unresolved_reason: Optional[str]
    entrypoint: Optional[str]
    command: Optional[str]
    launchers: Tuple[str, ...] = ()
    invocations: Tuple[ActionInvocation, ...] = ()
    custom_action_data: Tuple[PropertyAssignment, ...] = ()
    data_reference: Optional[DataReference] = None
    binary: Optional[BinaryPayloadInfo] = None
    script_preview: Optional[str] = None
    script_preview_truncated: bool = False
    decoded_powershell: Optional[DecodedPowerShellCommand] = None
    findings: Tuple[AnalysisFinding, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "type": self.type_info.to_dict(),
            "source": self.source,
            "target": self.target,
            "resolved_source": self.resolved_source,
            "resolved_target": self.resolved_target,
            "source_origin": self.source_origin,
            "unresolved_reason": self.unresolved_reason,
            "entrypoint": self.entrypoint,
            "command": self.command,
            "launchers": list(self.launchers),
            "invocations": [item.to_dict() for item in self.invocations],
            "custom_action_data": [item.to_dict() for item in self.custom_action_data],
            "data_reference": self.data_reference.to_dict() if self.data_reference else None,
            "binary": self.binary.to_dict() if self.binary else None,
            "script_preview": self.script_preview,
            "script_preview_truncated": self.script_preview_truncated,
            "decoded_powershell": (
                self.decoded_powershell.to_dict() if self.decoded_powershell else None
            ),
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass(frozen=True)
class PackageAnalysis:
    """Result returned by :func:`analyze_package`."""

    custom_actions: Tuple[CustomActionInfo, ...]
    findings: Tuple[AnalysisFinding, ...]
    warnings: Tuple[str, ...] = ()
    has_custom_action_table: bool = False
    registry_writes: Tuple[RegistryWriteInfo, ...] = ()
    registry_searches: Tuple[RegistrySearchInfo, ...] = ()
    service_controls: Tuple[ServiceControlInfo, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        priorities: DefaultDict[str, int] = defaultdict(int)
        for finding in self.findings:
            priorities[finding.review_priority] += 1
        invoked = sum(
            any(invocation.allowed for invocation in action.invocations)
            for action in self.custom_actions
        )
        unresolved = sum(action.unresolved_reason is not None for action in self.custom_actions)
        return {
            "custom_actions": [item.to_dict() for item in self.custom_actions],
            "findings": [item.to_dict() for item in self.findings],
            "warnings": list(self.warnings),
            "registry_writes": [item.to_dict() for item in self.registry_writes],
            "registry_searches": [item.to_dict() for item in self.registry_searches],
            "service_controls": [item.to_dict() for item in self.service_controls],
            "summary": {
                "has_custom_action_table": self.has_custom_action_table,
                "custom_action_count": len(self.custom_actions),
                "invoked_action_count": invoked,
                "unreferenced_action_count": len(self.custom_actions) - invoked,
                "script_action_count": sum(
                    action.type_info.kind in ("jscript", "vbscript")
                    for action in self.custom_actions
                ),
                "deferred_action_count": sum(
                    action.type_info.execution in ("deferred", "rollback", "commit")
                    for action in self.custom_actions
                ),
                "finding_count": len(self.findings),
                "persistence_finding_count": sum(
                    finding.category == "persistence" for finding in self.findings
                ),
                "unresolved_reference_count": unresolved,
                "registry_write_count": len(self.registry_writes),
                "registry_search_count": len(self.registry_searches),
                "service_control_count": len(self.service_controls),
                "categories": sorted({item.category for item in self.findings}),
                "review_priorities": dict(sorted(priorities.items())),
            },
        }


def _table_rows(table: Any) -> List[Mapping[str, Any]]:
    iterator = getattr(table, "iter", None)
    if callable(iterator):
        try:
            return list(iterator(True))
        except TypeError:
            pass
    return list(table)


def _rows(package: Any, table_name: str, warnings: List[str]) -> List[Mapping[str, Any]]:
    try:
        table = package.get(table_name)
        if table is None:
            return []
        return _table_rows(table)
    except Exception as exc:
        warnings.append(f"Could not read {table_name}: {exc}")
        return []


def _text(value: Any) -> Optional[str]:
    return None if value is None else str(value)


def _integer(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _long_name(value: Any) -> str:
    text = str(value or "")
    target = text.split(":", 1)[0]
    if "|" in target:
        target = target.split("|", 1)[1]
    return target


def _build_paths(
    file_rows: Sequence[Mapping[str, Any]],
    component_rows: Sequence[Mapping[str, Any]],
    directory_rows: Sequence[Mapping[str, Any]],
) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, str]]:
    component_directories = {
        str(row.get("Component")): str(row.get("Directory_"))
        for row in component_rows
        if row.get("Component") is not None and row.get("Directory_") is not None
    }
    directory_paths = {
        str(row.get("Directory")): f"[{row.get('Directory')}]"
        for row in directory_rows
        if row.get("Directory") is not None
    }

    def directory_path(key: str) -> str:
        return directory_paths.get(key, f"[{key}]")

    file_paths: Dict[str, str] = {}
    for row in file_rows:
        file_key = row.get("File")
        if file_key is None:
            continue
        component = row.get("Component_")
        directory = component_directories.get(str(component)) if component is not None else None
        file_name = _long_name(row.get("FileName")) or str(file_key)
        file_paths[str(file_key)] = (
            f"{directory_path(directory)}\\{file_name}"
            if directory
            else f"[#{file_key}] ({file_name})"
        )

    component_paths = {
        component: directory_path(directory)
        for component, directory in component_directories.items()
    }
    return file_paths, component_paths, directory_paths


def _component_file_paths(
    file_rows: Sequence[Mapping[str, Any]],
    component_rows: Sequence[Mapping[str, Any]],
    file_paths: Mapping[str, str],
) -> Dict[str, str]:
    candidates: Dict[str, List[str]] = {}
    for row in file_rows:
        component = row.get("Component_")
        file_key = row.get("File")
        if component is None or file_key is None:
            continue
        path = file_paths.get(str(file_key))
        if path is not None:
            candidates.setdefault(str(component), []).append(path)

    result: Dict[str, str] = {}
    for row in component_rows:
        component = row.get("Component")
        if component is None:
            continue
        component_id = str(component)
        key_path = row.get("KeyPath")
        if key_path is not None and str(key_path) in file_paths:
            result[component_id] = file_paths[str(key_path)]
        elif key_path is None and len(candidates.get(component_id, ())) == 1:
            result[component_id] = candidates[component_id][0]
    return result


def _resolve_formatted(
    value: Optional[str],
    properties: Mapping[str, str],
    file_paths: Mapping[str, str],
    component_paths: Mapping[str, str],
    directory_paths: Optional[Mapping[str, str]] = None,
    max_depth: int = 5,
) -> Optional[str]:
    if value is None:
        return None
    result = str(value)
    for _ in range(max_depth):
        changed = False

        def replace(match: re.Match) -> str:
            nonlocal changed
            token = match.group(1)
            replacement: Optional[str] = None
            is_directory = False
            if token.startswith(("#", "!")):
                replacement = file_paths.get(token[1:])
            elif token.startswith("$"):
                replacement = component_paths.get(token[1:])
            elif token in properties:
                replacement = properties[token]
            elif directory_paths is not None and token in directory_paths:
                replacement = directory_paths[token]
                is_directory = True
            if replacement is None:
                return match.group(0)
            if is_directory:
                next_character = match.string[match.end() : match.end() + 1]
                if next_character in ("\\", "/"):
                    replacement = replacement.rstrip("\\/")
                elif replacement and not replacement.endswith(("\\", "/")):
                    replacement += "\\"
            changed = True
            return replacement

        result = _PROPERTY_TOKEN.sub(replace, result)
        if not changed:
            break
    return result


def _decode_script(data: bytes, limit: int) -> Tuple[str, bool]:
    preview = data[:limit]
    encodings: List[str] = []
    if preview.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings.extend(("utf-16", "utf-8"))
    elif preview.count(b"\x00") > max(2, len(preview) // 8):
        encodings.extend(("utf-16-le", "utf-8"))
    else:
        encodings.extend(("utf-8-sig", "utf-16-le"))
    encodings.append("latin-1")
    text = ""
    for encoding in encodings:
        try:
            text = preview.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    truncated = len(data) > limit
    if truncated:
        text += f"\n... <{len(data) - limit} bytes omitted>"
    return text, truncated


def _guess_format(data: bytes) -> str:
    if data.startswith(b"MZ"):
        return "PE image"
    if data.startswith(b"MSCF"):
        return "CAB archive"
    if data.startswith(b"PK\x03\x04"):
        return "ZIP archive"
    if data.startswith(b"\x7fELF"):
        return "ELF image"
    if data.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")):
        return "text"
    sample = data[:4096]
    printable = sum(byte in b"\t\n\r" or 32 <= byte < 127 for byte in sample)
    if sample and printable / len(sample) > 0.85:
        return "text"
    return "binary"


def _read_binary_payload(
    package: Any,
    key: Optional[str],
    warnings: List[str],
) -> Tuple[Optional[bytes], Optional[BinaryPayloadInfo], Optional[str]]:
    if not key:
        return None, None, "Binary source key is empty"
    if not hasattr(package, "get_datastream_bytes"):
        return None, None, "Package object does not expose get_datastream_bytes()"
    reference = DataReference("Binary", (key,), f"Binary[{key}]")
    try:
        value = package.get_datastream_bytes("Binary", key)
    except Exception as exc:
        warnings.append(f"Could not read Binary[{key!r}]: {exc}")
        return None, None, f"Binary data stream could not be read: {exc}"
    if value is None:
        warnings.append(f"Binary[{key!r}] has no matching data stream.")
        return None, None, "Binary row has no matching data stream"
    data = bytes(value)
    return (
        data,
        BinaryPayloadInfo(
            reference=reference,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            format=_guess_format(data),
        ),
        None,
    )


def _find_launchers(value: Optional[str]) -> Tuple[str, ...]:
    if not value:
        return ()
    return tuple(dict.fromkeys(name for name, pattern in _LAUNCHERS if pattern.search(value)))


def decode_powershell_command(
    command: Optional[str],
    *,
    preview_bytes: int = DEFAULT_PREVIEW_BYTES,
    origin: Optional[str] = None,
) -> Optional[DecodedPowerShellCommand]:
    """Decode a PowerShell EncodedCommand argument when one is present.

    The command must first be recognized as a PowerShell or pwsh invocation.
    The returned plaintext is bounded even though the hash and decoded size
    describe the complete decoded byte string.
    """

    if preview_bytes < 0:
        raise ValueError("preview_bytes must be non-negative")
    if not command or not {"powershell", "pwsh"}.intersection(_find_launchers(command)):
        return None
    match = _POWERSHELL_ENCODED_ARGUMENT.search(command)
    if match is None:
        return None
    encoded = next(group for group in match.groups() if group is not None)
    compact = re.sub(r"\s+", "", encoded)
    padded = compact + "=" * (-len(compact) % 4)
    try:
        decoded = base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError) as exc:
        return DecodedPowerShellCommand(
            origin=origin,
            encoded_argument_length=len(encoded),
            decoded_size=None,
            sha256=None,
            encoding=None,
            text_preview=None,
            error=f"Base64 decode failed: {exc}",
        )

    encoding: Optional[str] = None
    text: Optional[str] = None
    if decoded.startswith((b"\xff\xfe", b"\xfe\xff")):
        candidates = ("utf-16", "utf-8-sig", "utf-8", "utf-16-le")
    else:
        odd_bytes = decoded[1::2]
        odd_zero_ratio = odd_bytes.count(0) / len(odd_bytes) if odd_bytes else 0.0
        # PowerShell documents EncodedCommand as UTF-16LE, and ordinary script
        # syntax generally produces NUL bytes in the odd positions.  Prefer
        # UTF-8 when that signal is absent so short ASCII payloads do not turn
        # into valid-looking but meaningless UTF-16 text.
        candidates = (
            ("utf-16-le", "utf-8-sig", "utf-8")
            if odd_zero_ratio >= 0.20
            else ("utf-8-sig", "utf-8", "utf-16-le")
        )
    for candidate in candidates:
        try:
            text = decoded.decode(candidate)
            encoding = candidate
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = decoded.decode("latin-1", errors="replace")
        encoding = "latin-1"

    if preview_bytes == 0:
        return DecodedPowerShellCommand(
            origin=origin,
            encoded_argument_length=len(encoded),
            decoded_size=len(decoded),
            sha256=hashlib.sha256(decoded).hexdigest(),
            encoding=encoding,
            text_preview=None,
            truncated=bool(decoded),
        )

    preview_size = min(len(decoded), preview_bytes)
    if encoding.startswith("utf-16") and preview_size % 2:
        preview_size -= 1
    preview_raw = decoded[:preview_size]
    try:
        preview = preview_raw.decode(encoding, errors="replace")
    except LookupError:
        preview = text[:preview_size]
    truncated = len(decoded) > preview_size
    if truncated:
        preview += f"\n... <{len(decoded) - preview_size} decoded bytes omitted>"
    return DecodedPowerShellCommand(
        origin=origin,
        encoded_argument_length=len(encoded),
        decoded_size=len(decoded),
        sha256=hashlib.sha256(decoded).hexdigest(),
        encoding=encoding,
        text_preview=preview,
        truncated=truncated,
    )


def _first_decoded_powershell(
    candidates: Iterable[Tuple[str, Optional[str]]], *, preview_bytes: int
) -> Optional[DecodedPowerShellCommand]:
    for origin, value in candidates:
        decoded = decode_powershell_command(
            value,
            preview_bytes=preview_bytes,
            origin=origin,
        )
        if decoded is not None:
            return decoded
    return None


def _command_parts(
    type_info: CustomActionTypeInfo,
    resolved_source: Optional[str],
    resolved_target: Optional[str],
) -> Optional[str]:
    if type_info.kind != "exe":
        return None
    if type_info.type_number in (2, 34):
        return resolved_target
    return " ".join(part for part in (resolved_source, resolved_target) if part).strip() or None


def _source_label(
    type_info: CustomActionTypeInfo,
    source: Optional[str],
    resolved_source: Optional[str],
) -> Optional[str]:
    if source is None:
        return None
    if type_info.source_kind == "binary":
        return f"Binary[{source}]"
    if type_info.source_kind == "file":
        return f"File[{source}] -> {resolved_source or source}"
    if type_info.source_kind == "property":
        return f"Property[{source}] -> {resolved_source or ''}".rstrip()
    if type_info.source_kind == "property-name":
        return f"Property[{source}]"
    if type_info.source_kind == "directory":
        return f"Directory[{source}] -> {resolved_source or source}"
    if type_info.source_kind == "substorage":
        return f"package substorage {source!r}"
    if type_info.source_kind == "source-path":
        return f"source-tree package {source!r}"
    if type_info.source_kind == "product-code":
        return f"product code {source}"
    return resolved_source or source


def _action_findings(
    action: str,
    type_info: CustomActionTypeInfo,
    source: Optional[str],
    target: Optional[str],
    resolved_source: Optional[str],
    command: Optional[str],
    launchers: Sequence[str],
    script_text: Optional[str],
    indirect_text: Optional[str],
    decoded_powershell: Optional[DecodedPowerShellCommand],
    data_reference: Optional[DataReference],
    custom_action_data: Sequence[PropertyAssignment],
    hidden_properties: Set[str],
    invocations: Sequence[ActionInvocation],
    unresolved_reason: Optional[str],
) -> List[AnalysisFinding]:
    findings: List[AnalysisFinding] = []

    if type_info.kind in ("jscript", "vbscript"):
        language = "JScript" if type_info.kind == "jscript" else "VBScript"
        location = {
            "binary": "stored in the Binary table",
            "file": "loaded from an installed file",
            "property": "read from a property",
            "none": "stored inline in the CustomAction row",
        }.get(type_info.source_kind, type_info.source_kind)
        findings.append(
            AnalysisFinding(
                "script",
                "medium",
                f"{language} custom action",
                f"{language} is {location}.",
                action=action,
                table="CustomAction",
                reference=data_reference,
            )
        )
    elif type_info.kind == "dll":
        detail = f"Calls DLL entry point {target!r}." if target else "Calls a DLL custom action."
        findings.append(
            AnalysisFinding(
                "executable",
                "low",
                "DLL custom action",
                detail,
                action=action,
                table="CustomAction",
                reference=data_reference,
            )
        )
    elif type_info.kind == "exe":
        findings.append(
            AnalysisFinding(
                "executable",
                "low",
                "Executable custom action",
                command
                or _source_label(type_info, source, resolved_source)
                or "Executes a program.",
                action=action,
                table="CustomAction",
                reference=data_reference,
            )
        )
    elif type_info.kind == "concurrent-install":
        findings.append(
            AnalysisFinding(
                "nested-install",
                "medium",
                "Concurrent/nested installation",
                _source_label(type_info, source, resolved_source)
                or "Runs a concurrent installation.",
                action=action,
                table="CustomAction",
            )
        )

    decoded_text = (
        decoded_powershell.text_preview
        if decoded_powershell is not None and decoded_powershell.error is None
        else None
    )
    inspected = "\n".join(
        part for part in (command, script_text, indirect_text, decoded_text) if part
    )
    command_launchers = set(_find_launchers(command))
    indirect_launchers = set(_find_launchers(indirect_text))
    for launcher in launchers:
        priority = (
            "high"
            if launcher in ("powershell", "pwsh", "mshta", "rundll32", "regsvr32")
            else "medium"
        )
        if launcher in command_launchers:
            detail = command or ""
        elif launcher in indirect_launchers:
            detail = f"CustomActionData: {indirect_text}"
        else:
            detail = "The script text contains this launcher name."
        findings.append(
            AnalysisFinding(
                "command-line",
                priority,
                f"Launches or references {launcher}",
                detail,
                action=action,
                table="CustomAction",
                reference=data_reference,
            )
        )

    uses_powershell = bool({"powershell", "pwsh"}.intersection(launchers))
    if decoded_powershell is not None:
        if decoded_powershell.error:
            detail = decoded_powershell.error
        else:
            detail = (
                f"Decoded {decoded_powershell.decoded_size} bytes as "
                f"{decoded_powershell.encoding}; SHA-256 {decoded_powershell.sha256}."
            )
        if decoded_powershell.origin:
            detail = f"{decoded_powershell.origin}: {detail}"
        findings.append(
            AnalysisFinding(
                "command-line",
                "high",
                "Encoded PowerShell command",
                detail,
                action=action,
                table="CustomAction",
            )
        )
    if uses_powershell and re.search(r"(?i)(?:-|/)(?:w|windowstyle)\s+(?:hidden|0)\b", inspected):
        findings.append(
            AnalysisFinding(
                "command-line",
                "medium",
                "Hidden PowerShell window",
                "The PowerShell command requests a hidden window.",
                action=action,
                table="CustomAction",
            )
        )
    if uses_powershell and re.search(r"(?i)(?:-|/)(?:nop|noprofile)\b", inspected):
        findings.append(
            AnalysisFinding(
                "command-line",
                "low",
                "PowerShell profile disabled",
                "The PowerShell command disables profile loading.",
                action=action,
                table="CustomAction",
            )
        )

    if _RUN_KEY_PATH.search(inspected):
        findings.append(
            AnalysisFinding(
                "persistence",
                "high",
                "References a registry Run key",
                command or "A script or indirect command references a registry Run key.",
                action=action,
                table="CustomAction",
            )
        )
    if re.search(r"(?i)\bschtasks(?:\.exe)?\b.*(?:/create|\bcreate\b)", inspected) or re.search(
        r"(?i)\b(?:register|new)-scheduledtask\b", inspected
    ):
        findings.append(
            AnalysisFinding(
                "persistence",
                "high",
                "Creates or changes a scheduled task",
                command or "A script references scheduled-task creation.",
                action=action,
                table="CustomAction",
            )
        )
    if re.search(r"(?i)\bsc(?:\.exe)?\s+(?:create|config)\b", inspected) or re.search(
        r"(?i)\bnew-service\b", inspected
    ):
        findings.append(
            AnalysisFinding(
                "persistence",
                "high",
                "Creates or reconfigures a service",
                command or "A script references service creation.",
                action=action,
                table="CustomAction",
            )
        )

    if type_info.execution in ("deferred", "rollback", "commit"):
        if custom_action_data:
            detail = "CustomActionData can be supplied by " + ", ".join(
                item.setter_action or f"Property[{item.property_name}]"
                for item in custom_action_data
            )
        else:
            detail = (
                f"The action can receive CustomActionData from property {action!r}; no simple "
                "Property row or type 51 setter was found."
            )
        findings.append(
            AnalysisFinding(
                "indirection",
                "medium",
                "Deferred CustomActionData",
                detail,
                action=action,
                table="CustomAction",
            )
        )

    if type_info.hide_target:
        findings.append(
            AnalysisFinding(
                "logging",
                "medium",
                "Target hidden from MSI log",
                "HideTarget suppresses Target and deferred CustomActionData in the action log.",
                action=action,
                table="CustomAction",
            )
        )
        if custom_action_data and action not in hidden_properties:
            findings.append(
                AnalysisFinding(
                    "logging",
                    "low",
                    "CustomActionData source property is not listed as hidden",
                    (
                        f"Property {action!r} is not in MsiHiddenProperties; its value may still "
                        "be logged when another action sets it."
                    ),
                    action=action,
                    table="Property",
                )
            )
    if "no impersonation" in type_info.flags:
        findings.append(
            AnalysisFinding(
                "privilege",
                "high" if type_info.kind in ("exe", "dll", "jscript", "vbscript") else "medium",
                "Runs without user impersonation",
                "The in-script action runs in the installer service context instead of impersonating the installing user.",
                action=action,
                table="CustomAction",
            )
        )
    if type_info.return_processing == "asynchronous; do not wait":
        findings.append(
            AnalysisFinding(
                "execution",
                "medium",
                "Installer does not wait for completion",
                "The custom action may continue after Windows Installer exits.",
                action=action,
                table="CustomAction",
            )
        )
    if unresolved_reason:
        findings.append(
            AnalysisFinding(
                "resolution",
                "medium",
                "CustomAction source could not be fully resolved",
                unresolved_reason,
                action=action,
                table="CustomAction",
                reference=data_reference,
            )
        )
    for invocation in invocations:
        if not invocation.allowed:
            findings.append(
                AnalysisFinding(
                    "validation",
                    "medium",
                    "Invalid or unreachable sequence reference",
                    f"{invocation.table}: {invocation.note or 'custom action is not allowed here'}",
                    action=action,
                    table=invocation.table,
                )
            )
    for warning in type_info.warnings:
        findings.append(
            AnalysisFinding(
                "validation",
                "medium",
                "Unusual CustomAction type flags",
                warning,
                action=action,
                table="CustomAction",
            )
        )
    return findings


def _registry_persistence_categories(key: str, name: Optional[str]) -> Tuple[str, ...]:
    normalized_key = key.strip("\\").lower()
    normalized_name = (name or "").lower()
    categories: List[str] = []
    if _RUN_KEY_PATH.search(key):
        categories.append("Run/RunOnce logon autostart")
    if normalized_key.endswith(
        r"software\microsoft\windows nt\currentversion\winlogon"
    ) and normalized_name in {
        "shell",
        "userinit",
        "system",
    }:
        categories.append("Winlogon autostart")
    if "image file execution options\\" in normalized_key and normalized_name == "debugger":
        categories.append("Image File Execution Options debugger")
    if "active setup\\installed components\\" in normalized_key and normalized_name == "stubpath":
        categories.append("Active Setup StubPath")
    if normalized_key.endswith(
        r"software\microsoft\windows nt\currentversion\windows"
    ) and normalized_name in {
        "appinit_dlls",
        "loadappinit_dlls",
    }:
        categories.append("AppInit DLL loading")
    if r"appcertdlls" in normalized_key:
        categories.append("AppCert DLL loading")
    if r"shellserviceobjectdelayload" in normalized_key:
        categories.append("Shell service object autostart")
    if "currentcontrolset\\services\\" in normalized_key and normalized_name == "imagepath":
        categories.append("Service ImagePath")
    return tuple(dict.fromkeys(categories))


def _registry_writes(
    rows: Iterable[Mapping[str, Any]],
    properties: Mapping[str, str],
    file_paths: Mapping[str, str],
    component_paths: Mapping[str, str],
    directory_paths: Mapping[str, str],
) -> Tuple[RegistryWriteInfo, ...]:
    result: List[RegistryWriteInfo] = []
    for row in rows:
        raw_key = _text(row.get("Key")) or ""
        key = (
            _resolve_formatted(raw_key, properties, file_paths, component_paths, directory_paths)
            or raw_key
        )
        root_value = _integer(row.get("Root"))
        root = _ROOT_NAMES.get(root_value, f"Root({root_value})")
        name = _text(row.get("Name"))
        value = _text(row.get("Value"))
        resolved = _resolve_formatted(
            value, properties, file_paths, component_paths, directory_paths
        )
        result.append(
            RegistryWriteInfo(
                root=root,
                key=key,
                name=name,
                value=value,
                resolved_value=resolved,
                component=_text(row.get("Component_")),
                persistence_categories=_registry_persistence_categories(key, name),
            )
        )
    return tuple(result)


def _registry_write_findings(writes: Sequence[RegistryWriteInfo]) -> List[AnalysisFinding]:
    findings: List[AnalysisFinding] = []
    for write in writes:
        for category in write.persistence_categories:
            name = write.name or "(default)"
            value = write.resolved_value if write.resolved_value is not None else write.value
            title = (
                "Registry Run-key persistence"
                if category == "Run/RunOnce logon autostart"
                else category
            )
            findings.append(
                AnalysisFinding(
                    "persistence",
                    "high",
                    title,
                    f"{write.root}\\{write.key} value {name!r} -> {value or ''}",
                    table="Registry",
                )
            )
    return findings


def _service_install_findings(
    rows: Iterable[Mapping[str, Any]],
    properties: Mapping[str, str],
    file_paths: Mapping[str, str],
    component_paths: Mapping[str, str],
    directory_paths: Mapping[str, str],
    component_file_paths: Mapping[str, str],
) -> List[AnalysisFinding]:
    start_types = {0: "boot", 1: "system", 2: "automatic", 3: "demand", 4: "disabled"}
    findings: List[AnalysisFinding] = []
    for row in rows:
        name = (
            _resolve_formatted(
                _text(row.get("Name")),
                properties,
                file_paths,
                component_paths,
                directory_paths,
            )
            or "(unnamed)"
        )
        arguments = _resolve_formatted(
            _text(row.get("Arguments")),
            properties,
            file_paths,
            component_paths,
            directory_paths,
        )
        start = _integer(row.get("StartType"))
        start_label = start_types.get(start, f"start type {start}")
        detail = f"Installs service {name!r} with {start_label} startup"
        component = _text(row.get("Component_"))
        binary_path = component_file_paths.get(component or "")
        if binary_path:
            detail += f"; binary: {binary_path}"
        if arguments:
            detail += f"; arguments: {arguments}"
        priority = "high" if start in (0, 1, 2) else "medium"
        findings.append(
            AnalysisFinding(
                "persistence",
                priority,
                "Service installation",
                detail,
                table="ServiceInstall",
            )
        )
    return findings


def _decode_service_control_events(value: int) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    known = {
        0x001: "start during install",
        0x002: "stop during install",
        0x008: "delete during install",
        0x010: "start during uninstall",
        0x020: "stop during uninstall",
        0x080: "delete during uninstall",
    }
    events = tuple(label for bit, label in known.items() if value & bit)
    warnings: List[str] = []
    if value & 0x004:
        warnings.append("Reserved install event bit 0x004 is set.")
    if value & 0x040:
        warnings.append("Reserved uninstall event bit 0x040 is set.")
    unknown = value & ~0x0FF
    if unknown:
        warnings.append(f"Unknown ServiceControl event bits are set: 0x{unknown:x}.")
    return events, tuple(warnings)


def _service_controls(
    rows: Iterable[Mapping[str, Any]],
    service_install_rows: Sequence[Mapping[str, Any]],
    properties: Mapping[str, str],
    file_paths: Mapping[str, str],
    component_paths: Mapping[str, str],
    directory_paths: Mapping[str, str],
) -> Tuple[ServiceControlInfo, ...]:
    installed_names: Set[str] = set()
    for row in service_install_rows:
        name = _resolve_formatted(
            _text(row.get("Name")), properties, file_paths, component_paths, directory_paths
        )
        if name:
            installed_names.add(name.lower())

    result: List[ServiceControlInfo] = []
    for row in rows:
        identifier = _text(row.get("ServiceControl")) or "(unnamed)"
        name = _text(row.get("Name")) or ""
        resolved_name = (
            _resolve_formatted(name, properties, file_paths, component_paths, directory_paths)
            or name
        )
        event_value = _integer(row.get("Event")) or 0
        events, warnings = _decode_service_control_events(event_value)
        arguments = _text(row.get("Arguments"))
        resolved_arguments = _resolve_formatted(
            arguments, properties, file_paths, component_paths, directory_paths
        )
        start_arguments = tuple(
            part for part in re.split(r"\[~\]|\x00", resolved_arguments or "") if part
        )
        wait = _integer(row.get("Wait"))
        if wait in (None, 1):
            wait_behavior = "wait up to 30 seconds for completion"
        elif wait == 0:
            wait_behavior = "wait only until the service reports a pending state"
        else:
            wait_behavior = f"nonstandard Wait value {wait}"
            warnings = warnings + (f"Wait should be null, 0, or 1; found {wait}.",)
        component = _text(row.get("Component_"))
        result.append(
            ServiceControlInfo(
                identifier=identifier,
                name=name,
                resolved_name=resolved_name,
                event_value=event_value,
                events=events,
                arguments=arguments,
                resolved_arguments=resolved_arguments,
                start_arguments=start_arguments,
                wait=wait,
                wait_behavior=wait_behavior,
                component=component,
                matches_installed_service=resolved_name.lower() in installed_names,
                warnings=warnings,
            )
        )
    return tuple(result)


def _service_control_findings(controls: Sequence[ServiceControlInfo]) -> List[AnalysisFinding]:
    findings: List[AnalysisFinding] = []
    for control in controls:
        if control.events:
            detail = f"Service {control.resolved_name!r}: {', '.join(control.events)}"
            if control.start_arguments:
                detail += f"; start arguments: {control.start_arguments!r}"
            detail += f"; {control.wait_behavior}"
            if not control.matches_installed_service:
                detail += "; no matching ServiceInstall row was found"
            priority = (
                "medium"
                if any(event.startswith(("start", "delete")) for event in control.events)
                else "low"
            )
            findings.append(
                AnalysisFinding(
                    "service-control",
                    priority,
                    "Controls a Windows service",
                    detail,
                    table="ServiceControl",
                )
            )
        for warning in control.warnings:
            findings.append(
                AnalysisFinding(
                    "validation",
                    "medium",
                    "Unusual ServiceControl event flags",
                    warning,
                    table="ServiceControl",
                )
            )
    return findings


def _startup_directory_ids(rows: Sequence[Mapping[str, Any]]) -> Set[str]:
    directories = {
        str(row.get("Directory")): row for row in rows if row.get("Directory") is not None
    }
    result: Set[str] = set()
    for directory in directories:
        current = directory
        seen: Set[str] = set()
        while current and current not in seen:
            seen.add(current)
            row = directories.get(current)
            default_name = _long_name(row.get("DefaultDir")) if row is not None else ""
            if "startup" in current.lower() or "startup" in default_name.lower():
                result.add(directory)
                break
            parent = row.get("Directory_Parent") if row is not None else None
            current = str(parent) if parent is not None else ""
    return result


def _startup_shortcut_findings(
    rows: Iterable[Mapping[str, Any]],
    properties: Mapping[str, str],
    file_paths: Mapping[str, str],
    component_paths: Mapping[str, str],
    directory_paths: Mapping[str, str],
    startup_directories: Set[str],
) -> List[AnalysisFinding]:
    findings: List[AnalysisFinding] = []
    for row in rows:
        directory = str(row.get("Directory_") or "")
        if "startup" not in directory.lower() and directory not in startup_directories:
            continue
        shortcut = str(row.get("Name") or row.get("Shortcut") or "(unnamed)")
        raw_target = _text(row.get("Target")) or ""
        raw_arguments = _text(row.get("Arguments")) or ""
        target = (
            _resolve_formatted(raw_target, properties, file_paths, component_paths, directory_paths)
            or raw_target
        )
        arguments = (
            _resolve_formatted(
                raw_arguments, properties, file_paths, component_paths, directory_paths
            )
            or raw_arguments
        )
        detail = f"Shortcut {shortcut!r} in {directory} -> {target} {arguments}".rstrip()
        findings.append(
            AnalysisFinding(
                "persistence",
                "high",
                "Startup-folder shortcut",
                detail,
                table="Shortcut",
            )
        )
    return findings


def _property_references_in_action(action: CustomActionInfo, property_name: str) -> bool:
    token = f"[{property_name}]"
    if action.source == property_name and action.type_info.source_kind == "property":
        return True
    values = (
        action.source,
        action.target,
        action.resolved_source,
        action.resolved_target,
        action.command,
    )
    if any(value and token in value for value in values):
        return True
    if any(
        invocation.condition
        and re.search(
            rf"(?<![A-Za-z0-9_]){re.escape(property_name)}(?![A-Za-z0-9_])", invocation.condition
        )
        for invocation in action.invocations
    ):
        return True
    return any(
        token in assignment.value or token in assignment.resolved_value
        for assignment in action.custom_action_data
    )


def _registry_searches(
    reglocator_rows: Sequence[Mapping[str, Any]],
    appsearch_rows: Sequence[Mapping[str, Any]],
    signature_rows: Sequence[Mapping[str, Any]],
    properties: Mapping[str, str],
    file_paths: Mapping[str, str],
    component_paths: Mapping[str, str],
    directory_paths: Mapping[str, str],
    custom_actions: Sequence[CustomActionInfo],
) -> Tuple[RegistrySearchInfo, ...]:
    signature_properties: DefaultDict[str, List[str]] = defaultdict(list)
    for row in appsearch_rows:
        signature = _text(row.get("Signature_"))
        property_name = _text(row.get("Property"))
        if signature and property_name:
            signature_properties[signature].append(property_name)
    file_signatures = {
        str(row.get("Signature")) for row in signature_rows if row.get("Signature") is not None
    }

    result: List[RegistrySearchInfo] = []
    for row in reglocator_rows:
        signature = _text(row.get("Signature_"))
        if not signature:
            continue
        locator_type = _integer(row.get("Type"))
        if locator_type is None:
            locator_type = 1
        base_type = locator_type & 0x0F
        row_warnings: List[str] = []
        locator_kind = {
            0: "registry value contains a directory",
            1: "registry value contains a file name",
            2: "raw registry value",
        }.get(base_type, f"unknown locator type {base_type}")
        if base_type not in (0, 1, 2):
            row_warnings.append(f"RegLocator Type has invalid base value {base_type}.")
        unknown_bits = locator_type & ~0x13
        if unknown_bits:
            row_warnings.append(f"Unknown RegLocator Type bits are set: 0x{unknown_bits:x}.")
        signature_is_file = signature in file_signatures
        if signature_is_file:
            result_kind = "file matching Signature-table criteria"
            if base_type == 2:
                row_warnings.append(
                    "A Signature-table row takes precedence over RawValue semantics."
                )
        elif base_type == 2:
            result_kind = "raw registry value"
        else:
            result_kind = "directory path (signature is absent from Signature table)"
        property_names = tuple(dict.fromkeys(signature_properties.get(signature, ())))
        for property_name in property_names:
            if property_name.upper() != property_name:
                row_warnings.append(
                    f"AppSearch property {property_name!r} is not a public all-uppercase property."
                )
        referenced = tuple(
            action.action
            for action in custom_actions
            if any(_property_references_in_action(action, name) for name in property_names)
        )
        initial_values = tuple(
            (name, properties[name]) for name in property_names if name in properties
        )
        root_value = _integer(row.get("Root"))
        if root_value not in _REGLOCATOR_ROOT_NAMES:
            row_warnings.append(f"RegLocator Root has unsupported value {root_value!r}.")
        name = _text(row.get("Name"))
        result.append(
            RegistrySearchInfo(
                signature=signature,
                properties=property_names,
                root=_REGLOCATOR_ROOT_NAMES.get(root_value, f"Root({root_value})"),
                key=_text(row.get("Key")) or "",
                name=name,
                resolved_name=_resolve_formatted(
                    name,
                    properties,
                    file_paths,
                    component_paths,
                    directory_paths,
                ),
                locator_type=locator_type,
                locator_kind=locator_kind,
                result_kind=result_kind,
                registry_view="64-bit" if locator_type & 0x10 else "32-bit",
                signature_is_file=signature_is_file,
                initial_values=initial_values,
                referenced_by_custom_actions=referenced,
                warnings=tuple(row_warnings),
            )
        )
    return tuple(result)


def _registry_search_findings(searches: Sequence[RegistrySearchInfo]) -> List[AnalysisFinding]:
    findings: List[AnalysisFinding] = []
    for search in searches:
        if not search.referenced_by_custom_actions:
            pass
        else:
            properties = ", ".join(search.properties) or "an AppSearch property"
            initial = (
                "; initial fallback value(s): "
                + ", ".join(f"{name}={value!r}" for name, value in search.initial_values)
                if search.initial_values
                else ""
            )
            findings.append(
                AnalysisFinding(
                    "environment-discovery",
                    "medium",
                    "CustomAction references a registry-backed AppSearch result",
                    (
                        f"{properties} can be populated from {search.root}\\{search.key} "
                        f"({search.result_kind}, {search.registry_view} view) and is referenced by "
                        f"{', '.join(search.referenced_by_custom_actions)}{initial}."
                    ),
                    table="RegLocator/AppSearch",
                )
            )
        for warning in search.warnings:
            findings.append(
                AnalysisFinding(
                    "validation",
                    "low",
                    "Unusual RegLocator/AppSearch authoring",
                    f"Signature {search.signature!r}: {warning}",
                    table="RegLocator/AppSearch",
                )
            )
    return findings


def _analyze_custom_actions(
    package: Any,
    *,
    script_preview_bytes: int,
) -> Tuple[Tuple[CustomActionInfo, ...], CustomActionCollection, Tuple[str, ...]]:
    if script_preview_bytes < 0:
        raise ValueError("script_preview_bytes must be non-negative")

    collection = collect_custom_actions(package)
    warnings: List[str] = list(collection.warnings)
    properties = {
        str(row.get("Property")): str(row.get("Value") or "")
        for row in _rows(package, "Property", warnings)
        if row.get("Property") is not None
    }
    hidden_properties = {
        item.strip()
        for item in properties.get("MsiHiddenProperties", "").split(";")
        if item.strip()
    }
    file_rows = _rows(package, "File", warnings)
    component_rows = _rows(package, "Component", warnings)
    directory_rows = _rows(package, "Directory", warnings)
    file_paths, component_paths, directory_paths = _build_paths(
        file_rows, component_rows, directory_rows
    )
    file_ids = {str(row.get("File")) for row in file_rows if row.get("File") is not None}

    setters: DefaultDict[str, List[PropertyAssignment]] = defaultdict(list)
    for record in collection.actions:
        if record.type_info.type_number != 51:
            continue
        property_name = record.source
        value = record.target or ""
        if not property_name:
            continue
        setters[property_name].append(
            PropertyAssignment(
                property_name=property_name,
                value=value,
                resolved_value=(
                    _resolve_formatted(
                        value,
                        properties,
                        file_paths,
                        component_paths,
                        directory_paths,
                    )
                    or value
                ),
                setter_action=record.action,
                invocations=record.invocations,
            )
        )

    result: List[CustomActionInfo] = []
    for record in collection.actions:
        action = record.action
        type_info = record.type_info
        source = record.source
        target = record.target
        unresolved_reason: Optional[str] = None

        if type_info.source_kind == "property":
            raw_source_value = properties.get(source or "")
            resolved_source = _resolve_formatted(
                raw_source_value,
                properties,
                file_paths,
                component_paths,
                directory_paths,
            )
            if source and raw_source_value is None:
                unresolved_reason = f"Property {source!r} has no initial Property-table value; it may be set at runtime."
        elif type_info.source_kind == "file":
            resolved_source = file_paths.get(source or "")
            if source and source not in file_ids:
                unresolved_reason = f"File table has no row for source key {source!r}."
            if resolved_source is None:
                resolved_source = source
        elif type_info.source_kind == "directory":
            resolved_source = directory_paths.get(source or "")
            if source and resolved_source is None:
                unresolved_reason = f"Directory table has no row for source key {source!r}."
                resolved_source = source
        elif type_info.source_kind == "property-name":
            resolved_source = properties.get(source or "")
        else:
            resolved_source = source
        resolved_target = _resolve_formatted(
            target, properties, file_paths, component_paths, directory_paths
        )

        data_reference: Optional[DataReference] = None
        binary: Optional[BinaryPayloadInfo] = None
        binary_data: Optional[bytes] = None
        if type_info.source_kind == "binary" and source:
            data_reference = DataReference("Binary", (source,), f"Binary[{source}]")
            binary_data, binary, binary_error = _read_binary_payload(package, source, warnings)
            unresolved_reason = unresolved_reason or binary_error

        script_preview = None
        script_preview_truncated = False
        if type_info.kind in ("jscript", "vbscript"):
            if type_info.type_number in (37, 38):
                if target is not None:
                    encoded = target.encode("utf-8", errors="replace")
                    script_preview, script_preview_truncated = (
                        _decode_script(encoded, script_preview_bytes)
                        if script_preview_bytes
                        else (None, bool(encoded))
                    )
            elif type_info.source_kind == "property":
                if resolved_source is not None:
                    encoded = resolved_source.encode("utf-8", errors="replace")
                    script_preview, script_preview_truncated = (
                        _decode_script(encoded, script_preview_bytes)
                        if script_preview_bytes
                        else (None, bool(encoded))
                    )
            elif binary_data is not None and script_preview_bytes:
                script_preview, script_preview_truncated = _decode_script(
                    binary_data, script_preview_bytes
                )

        command = _command_parts(type_info, resolved_source, resolved_target)

        assignments: List[PropertyAssignment] = []
        if type_info.execution in ("deferred", "rollback", "commit"):
            if action in properties:
                value = properties[action]
                assignments.append(
                    PropertyAssignment(
                        property_name=action,
                        value=value,
                        resolved_value=(
                            _resolve_formatted(
                                value,
                                properties,
                                file_paths,
                                component_paths,
                                directory_paths,
                            )
                            or value
                        ),
                    )
                )
            assignments.extend(setters.get(action, ()))

        indirect_text = "\n".join(
            item.resolved_value for item in assignments if item.resolved_value
        )
        decoded_powershell = _first_decoded_powershell(
            (
                ("command line", command),
                ("CustomActionData", indirect_text or None),
                ("script preview", script_preview),
            ),
            preview_bytes=script_preview_bytes,
        )
        inspected_text = "\n".join(
            part
            for part in (
                command,
                script_preview,
                indirect_text,
                decoded_powershell.text_preview
                if decoded_powershell is not None and decoded_powershell.error is None
                else None,
            )
            if part
        )
        launchers = _find_launchers(inspected_text)
        entrypoint = target if type_info.target_kind in ("entrypoint", "function") else None
        findings = _action_findings(
            action,
            type_info,
            source,
            target,
            resolved_source,
            command,
            launchers,
            script_preview,
            indirect_text or None,
            decoded_powershell,
            data_reference,
            assignments,
            hidden_properties,
            record.invocations,
            unresolved_reason,
        )
        result.append(
            CustomActionInfo(
                action=action,
                type_info=type_info,
                source=source,
                target=target,
                resolved_source=resolved_source,
                resolved_target=resolved_target,
                source_origin=type_info.source_kind,
                unresolved_reason=unresolved_reason,
                entrypoint=entrypoint,
                command=command,
                launchers=launchers,
                invocations=record.invocations,
                custom_action_data=tuple(assignments),
                data_reference=data_reference,
                binary=binary,
                script_preview=script_preview,
                script_preview_truncated=script_preview_truncated,
                decoded_powershell=decoded_powershell,
                findings=tuple(findings),
            )
        )
    return tuple(result), collection, tuple(dict.fromkeys(warnings))


def analyze_custom_actions(
    package: Any,
    *,
    script_preview_bytes: int = DEFAULT_PREVIEW_BYTES,
) -> Tuple[CustomActionInfo, ...]:
    """Interpret CustomAction rows in a Package-like object."""

    actions, _collection, _warnings = _analyze_custom_actions(
        package, script_preview_bytes=script_preview_bytes
    )
    return actions


def analyze_package(
    package: Any, *, script_preview_bytes: int = DEFAULT_PREVIEW_BYTES
) -> PackageAnalysis:
    """Produce a lightweight static behavior overview of an MSI package."""

    custom_actions, collection, action_warnings = _analyze_custom_actions(
        package, script_preview_bytes=script_preview_bytes
    )
    warnings = list(action_warnings)
    properties = {
        str(row.get("Property")): str(row.get("Value") or "")
        for row in _rows(package, "Property", warnings)
        if row.get("Property") is not None
    }
    file_rows = _rows(package, "File", warnings)
    component_rows = _rows(package, "Component", warnings)
    directory_rows = _rows(package, "Directory", warnings)
    file_paths, component_paths, directory_paths = _build_paths(
        file_rows, component_rows, directory_rows
    )
    component_file_paths = _component_file_paths(file_rows, component_rows, file_paths)
    startup_directories = _startup_directory_ids(directory_rows)

    registry_writes = _registry_writes(
        _rows(package, "Registry", warnings),
        properties,
        file_paths,
        component_paths,
        directory_paths,
    )
    service_install_rows = _rows(package, "ServiceInstall", warnings)
    service_controls = _service_controls(
        _rows(package, "ServiceControl", warnings),
        service_install_rows,
        properties,
        file_paths,
        component_paths,
        directory_paths,
    )
    registry_searches = _registry_searches(
        _rows(package, "RegLocator", warnings),
        _rows(package, "AppSearch", warnings),
        _rows(package, "Signature", warnings),
        properties,
        file_paths,
        component_paths,
        directory_paths,
        custom_actions,
    )

    findings: List[AnalysisFinding] = []
    for action in custom_actions:
        findings.extend(action.findings)
    findings.extend(_registry_write_findings(registry_writes))
    findings.extend(
        _service_install_findings(
            service_install_rows,
            properties,
            file_paths,
            component_paths,
            directory_paths,
            component_file_paths,
        )
    )
    findings.extend(_service_control_findings(service_controls))
    findings.extend(
        _startup_shortcut_findings(
            _rows(package, "Shortcut", warnings),
            properties,
            file_paths,
            component_paths,
            directory_paths,
            startup_directories,
        )
    )
    findings.extend(_registry_search_findings(registry_searches))
    return PackageAnalysis(
        custom_actions=custom_actions,
        findings=tuple(findings),
        warnings=tuple(dict.fromkeys(warnings)),
        has_custom_action_table=collection.has_custom_action_table,
        registry_writes=registry_writes,
        registry_searches=registry_searches,
        service_controls=service_controls,
    )


def analyze_installer(
    package: Any, *, script_preview_bytes: int = DEFAULT_PREVIEW_BYTES
) -> PackageAnalysis:
    """Alias for :func:`analyze_package` using installer-oriented terminology."""

    return analyze_package(package, script_preview_bytes=script_preview_bytes)


def _indent_lines(value: str, prefix: str = "      ") -> List[str]:
    return [f"{prefix}{line}" for line in (value.splitlines() or [""])]


def format_analysis(analysis: PackageAnalysis) -> str:
    """Render :class:`PackageAnalysis` as CLI-friendly plain text."""

    lines = [
        "MSI installer analysis",
        "Static capability and behavior summary; review priority is not a malware verdict.",
        "",
    ]
    if not analysis.has_custom_action_table:
        lines.append("No CustomAction rows found; the package has no CustomAction table.")
    elif not analysis.custom_actions:
        lines.append("No CustomAction rows found; the CustomAction table is present but empty.")
    for item in analysis.custom_actions:
        flags = f" · {', '.join(item.type_info.flags)}" if item.type_info.flags else ""
        lines.append(f'CustomAction "{item.action}"')
        lines.append(
            f"  Type {item.type_info.value} ({item.type_info.value:#06x}) · "
            f"type number {item.type_info.type_number} · {item.type_info.summary}{flags}"
        )
        lines.append(f"  Return: {item.type_info.return_processing}")
        source = _source_label(item.type_info, item.source, item.resolved_source)
        if source:
            lines.append(f"  Source: {source}")
        if item.unresolved_reason:
            lines.append(f"  Unresolved: {item.unresolved_reason}")
        if item.binary:
            lines.append(
                f"  Payload: {item.binary.size} bytes · {item.binary.format} · "
                f"SHA-256 {item.binary.sha256}"
            )
        if item.entrypoint:
            lines.append(f"  Entry point/function: {item.entrypoint}")
        if (
            item.resolved_target
            and not item.command
            and not item.entrypoint
            and item.type_info.kind not in ("jscript", "vbscript")
        ):
            lines.append(f"  Target: {item.resolved_target}")
        if item.type_info.extended_type:
            lines.append(
                f"  ExtendedType {item.type_info.extended_type} "
                f"({item.type_info.extended_type:#06x})"
            )
        if item.command:
            lines.append("  Command line")
            lines.extend(_indent_lines(item.command))
        if item.launchers:
            lines.append(
                "  Launcher references (command, script, or CustomActionData): "
                + ", ".join(item.launchers)
            )
        if item.decoded_powershell:
            decoded = item.decoded_powershell
            origin = f" from {decoded.origin}" if decoded.origin else ""
            if decoded.error:
                lines.append(f"  Encoded PowerShell{origin}: {decoded.error}")
            elif decoded.text_preview is not None:
                lines.append(
                    f"  Decoded PowerShell{origin} ({decoded.decoded_size} bytes, {decoded.encoding}, "
                    f"SHA-256 {decoded.sha256})"
                )
                lines.extend(_indent_lines(decoded.text_preview))
        if item.script_preview:
            truncated = " (truncated)" if item.script_preview_truncated else ""
            lines.append(f"  Script preview{truncated}")
            lines.extend(_indent_lines(item.script_preview))
        if item.invocations:
            lines.append("  Referenced from:")
            for invocation in item.invocations:
                condition = f" if {invocation.condition}" if invocation.condition else ""
                number = f" @ {invocation.sequence}" if invocation.sequence is not None else ""
                trigger = f" ({invocation.trigger})" if invocation.trigger else ""
                invalid = " [invalid/unreachable]" if not invocation.allowed else ""
                lines.append(f"    {invocation.table}{number}{trigger}{condition}{invalid}")
                if invocation.note:
                    lines.append(f"      {invocation.note}")
        if item.custom_action_data:
            lines.append("  Deferred action reads CustomActionData:")
            for assignment in item.custom_action_data:
                setter = (
                    f' set by CustomAction "{assignment.setter_action}"'
                    if assignment.setter_action
                    else ""
                )
                lines.append(
                    f"    Property[{assignment.property_name}]{setter} -> "
                    f"{assignment.resolved_value}"
                )
        review_items = [
            finding for finding in item.findings if finding.category not in ("executable", "script")
        ]
        if review_items:
            lines.append("  Review items:")
            for finding in review_items:
                lines.append(f"    [{finding.review_priority}] {finding.category}: {finding.title}")
                if finding.detail and finding.detail != item.command:
                    lines.extend(_indent_lines(finding.detail, "      "))
        lines.append("")

    package_findings = [
        finding
        for finding in analysis.findings
        if finding.action is None
        and finding.category not in ("environment-discovery", "service-control")
    ]
    if package_findings:
        lines.append("Package-level review items")
        for finding in package_findings:
            lines.append(f"  [{finding.review_priority}] {finding.category}: {finding.title}")
            lines.extend(_indent_lines(finding.detail, "    "))
        lines.append("")

    if analysis.registry_searches:
        lines.append("Registry-backed AppSearch facts")
        for search in analysis.registry_searches:
            properties = ", ".join(search.properties) or "(no AppSearch property found)"
            name = (
                search.resolved_name
                if search.resolved_name is not None
                else search.name
                if search.name is not None
                else "(default)"
            )
            lines.append(
                f"  {properties} <- {search.root}\\{search.key} value {name!r} · "
                f"{search.locator_kind} · result: {search.result_kind} · "
                f"{search.registry_view} view"
            )
            if search.initial_values:
                lines.append(
                    "    Initial fallback: "
                    + ", ".join(
                        f"{property_name}={value!r}"
                        for property_name, value in search.initial_values
                    )
                )
            if search.referenced_by_custom_actions:
                lines.append(
                    "    [medium review] Referenced by CustomAction(s): "
                    f"{', '.join(search.referenced_by_custom_actions)}"
                )
            for warning in search.warnings:
                lines.append(f"    Warning: {warning}")
        lines.append("")

    if analysis.service_controls:
        lines.append("ServiceControl facts")
        for control in analysis.service_controls:
            events = ", ".join(control.events) or "no recognized event bits"
            priority = (
                "medium"
                if any(event.startswith(("start", "delete")) for event in control.events)
                else "low"
            )
            lines.append(f"  [{priority} review] {control.resolved_name}: {events}")
            if control.start_arguments:
                lines.append(f"    Start arguments: {', '.join(control.start_arguments)}")
            lines.append(f"    Wait: {control.wait_behavior}")
            if not control.matches_installed_service:
                lines.append("    No matching ServiceInstall row found")
            for warning in control.warnings:
                lines.append(f"    Warning: {warning}")
        lines.append("")

    if analysis.warnings:
        lines.append("Analysis warnings")
        lines.extend(f"  - {warning}" for warning in analysis.warnings)
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ActionInvocation",
    "AnalysisFinding",
    "BinaryPayloadInfo",
    "CustomActionCollection",
    "CustomActionInfo",
    "CustomActionRecord",
    "CustomActionTypeInfo",
    "DEFAULT_PREVIEW_BYTES",
    "DataReference",
    "DecodedPowerShellCommand",
    "PackageAnalysis",
    "PropertyAssignment",
    "RegistrySearchInfo",
    "RegistryWriteInfo",
    "ServiceControlInfo",
    "analyze_custom_actions",
    "analyze_installer",
    "analyze_package",
    "collect_custom_actions",
    "decode_custom_action_type",
    "decode_powershell_command",
    "format_analysis",
    "format_custom_actions",
    "load_custom_actions",
]
