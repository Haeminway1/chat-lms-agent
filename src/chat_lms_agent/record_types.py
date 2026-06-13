from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, Literal, cast

from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

RECORD_TYPE_SCHEMA_VERSION: Final = "record-type-v1"
REPO_RECORD_TYPES_DIR: Final = "assets/record-types"
PROFILE_RECORD_TYPES_DIR: Final = "record-types"

type RecordFieldType = Literal["string", "text", "number", "bool", "date", "enum"]
type RecordTarget = Literal["learner", "class", "lesson"]
type RecordTypeSource = Literal["repo", "profile"]

_FIELD_TYPES: Final = frozenset({"string", "text", "number", "bool", "date", "enum"})
_TARGETS: Final = frozenset({"learner", "class", "lesson"})


@dataclass(frozen=True, slots=True)
class RecordField:
    name: str
    field_type: RecordFieldType
    required: bool
    label: str
    options: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecordType:
    type_id: str
    schema_version: str
    label: str
    target: RecordTarget
    summary: str
    fields: tuple[RecordField, ...]
    source: RecordTypeSource


def load_record_types(
    repo_root: Path,
    profile: ProfileState | None = None,
) -> tuple[list[RecordType], list[str]]:
    record_types: dict[str, RecordType] = {}
    warnings: list[str] = []
    _load_dir(repo_root / REPO_RECORD_TYPES_DIR, "repo", record_types, warnings)
    if profile is not None:
        _load_dir(
            profile.root / STATE_DIR / PROFILE_RECORD_TYPES_DIR,
            "profile",
            record_types,
            warnings,
        )
    return [record_types[type_id] for type_id in sorted(record_types)], warnings


def record_types_list_json(
    repo_root: Path,
    profile: ProfileState | None = None,
) -> dict[str, JsonValue]:
    record_types, warnings = load_record_types(repo_root, profile)
    entries: list[JsonValue] = [_record_type_json(record_type) for record_type in record_types]
    return {"status": "PASS", "record_types": entries, "warnings": [*warnings]}


def define_record_type(
    profile: ProfileState,
    payload: dict[str, JsonValue],
) -> tuple[int, dict[str, JsonValue]]:
    error = _record_type_error(payload)
    if error is not None:
        return 2, {"status": "ERROR", "error_code": error}
    type_id = payload.get("id")
    if not isinstance(type_id, str) or not type_id.strip():
        return 2, {"status": "ERROR", "error_code": "MISSING_ID"}
    directory = profile.root / STATE_DIR / PROFILE_RECORD_TYPES_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{type_id}.json"
    _ = path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0, {
        "status": "PASS",
        "id": type_id,
        "source": "profile",
        "path": f"<profile-root>/{STATE_DIR}/{PROFILE_RECORD_TYPES_DIR}/{type_id}.json",
    }


def _load_dir(
    directory: Path,
    source: RecordTypeSource,
    record_types: dict[str, RecordType],
    warnings: list[str],
) -> None:
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.json")):
        record_type, warning = _parse_record_type(path, source)
        if warning is not None:
            warnings.append(warning)
            continue
        if record_type is not None:
            record_types[record_type.type_id] = record_type


def _parse_record_type(
    path: Path,
    source: RecordTypeSource,
) -> tuple[RecordType | None, str | None]:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return None, f"{path.name}: INVALID_JSON"
    if not isinstance(payload, dict):
        return None, f"{path.name}: NOT_AN_OBJECT"
    error = _record_type_error(payload)
    if error is not None:
        return None, f"{path.name}: {error}"
    type_id = payload.get("id")
    target = payload.get("target")
    return (
        RecordType(
            type_id=type_id if isinstance(type_id, str) else "",
            schema_version=RECORD_TYPE_SCHEMA_VERSION,
            label=_string(payload.get("label")),
            target=_target(target),
            summary=_string(payload.get("summary")),
            fields=_fields_tuple(payload.get("fields")),
            source=source,
        ),
        None,
    )


def _record_type_error(payload: dict[str, JsonValue]) -> str | None:
    root_error = _record_type_root_error(payload)
    if root_error is not None:
        return root_error
    fields = payload.get("fields")
    if not isinstance(fields, list):
        return "INVALID_FIELDS"
    return _fields_error(fields)


def _record_type_root_error(payload: dict[str, JsonValue]) -> str | None:
    if payload.get("schema_version") != RECORD_TYPE_SCHEMA_VERSION:
        return "UNSUPPORTED_SCHEMA_VERSION"
    type_id = payload.get("id")
    if not isinstance(type_id, str) or not type_id.strip():
        return "MISSING_ID"
    label = payload.get("label")
    if not isinstance(label, str):
        return "INVALID_LABEL"
    target = payload.get("target")
    if not isinstance(target, str) or target not in _TARGETS:
        return "INVALID_TARGET"
    return None


def _fields_error(fields: list[JsonValue]) -> str | None:
    for field in fields:
        if not isinstance(field, dict):
            return "INVALID_FIELD"
        error = _field_error(field)
        if error is not None:
            return error
    return None


def _field_error(field: dict[str, JsonValue]) -> str | None:
    base_error = _field_base_error(field)
    if base_error is not None:
        return base_error
    field_type = field.get("type")
    if field_type == "enum" and not _string_tuple(field.get("options")):
        return "ENUM_REQUIRES_OPTIONS"
    return None


def _field_base_error(field: dict[str, JsonValue]) -> str | None:
    name = field.get("name")
    if not isinstance(name, str) or not name.strip():
        return "INVALID_FIELD_NAME"
    field_type = field.get("type")
    if not isinstance(field_type, str) or field_type not in _FIELD_TYPES:
        return "INVALID_FIELD_TYPE"
    required = field.get("required", False)
    if not isinstance(required, bool):
        return "INVALID_FIELD_REQUIRED"
    label = field.get("label", "")
    if not isinstance(label, str):
        return "INVALID_FIELD_LABEL"
    return None


def _record_type_json(record_type: RecordType) -> dict[str, JsonValue]:
    fields: list[JsonValue] = [_field_json(field) for field in record_type.fields]
    return {
        "id": record_type.type_id,
        "label": record_type.label,
        "source": record_type.source,
        "target": record_type.target,
        "fields": fields,
    }


def _field_json(field: RecordField) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "name": field.name,
        "type": field.field_type,
        "required": field.required,
    }
    if field.label:
        payload["label"] = field.label
    if field.options:
        payload["options"] = [*field.options]
    return payload


def _fields_tuple(value: JsonValue | None) -> tuple[RecordField, ...]:
    if not isinstance(value, list):
        return ()
    fields: list[RecordField] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        fields.append(
            RecordField(
                name=_string(item.get("name")),
                field_type=_field_type(item.get("type")),
                required=_bool(item.get("required")),
                label=_string(item.get("label")),
                options=_string_tuple(item.get("options")),
            ),
        )
    return tuple(fields)


def _field_type(value: JsonValue | None) -> RecordFieldType:
    field_type: RecordFieldType = "string"
    match value:
        case "text":
            field_type = "text"
        case "number":
            field_type = "number"
        case "bool":
            field_type = "bool"
        case "date":
            field_type = "date"
        case "enum":
            field_type = "enum"
        case _:
            field_type = "string"
    return field_type


def _target(value: JsonValue | None) -> RecordTarget:
    match value:
        case "class":
            return "class"
        case "lesson":
            return "lesson"
        case _:
            return "learner"


def _string(value: JsonValue | None) -> str:
    if isinstance(value, str):
        return value
    return ""


def _bool(value: JsonValue | None) -> bool:
    if isinstance(value, bool):
        return value
    return False


def _string_tuple(value: JsonValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())
