from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, TextIO, cast

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

FILE_KEYS: Final = frozenset({"changed_files", "changedFiles", "file_path", "filePath"})


@dataclass(frozen=True, slots=True)
class HookPayload:
    event_name: str
    changed_files: tuple[str, ...]
    session_id: str | None
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InvalidHookPayload:
    error_code: str
    message: str


type HookPayloadResult = HookPayload | InvalidHookPayload


def read_hook_payload(stdin: TextIO, *, event_name: str) -> HookPayloadResult:
    raw = _read_stdin(stdin)
    if raw == "":
        return HookPayload(event_name=event_name, changed_files=(), session_id=None, warnings=())
    try:
        payload = cast("JsonValue", json.loads(raw))
    except JSONDecodeError:
        return InvalidHookPayload(
            error_code="INVALID_HOOK_PAYLOAD",
            message="hook stdin must be valid JSON",
        )
    if not isinstance(payload, dict):
        return InvalidHookPayload(
            error_code="INVALID_HOOK_PAYLOAD",
            message="hook stdin JSON must be an object",
        )
    return HookPayload(
        event_name=_event_name(payload, event_name),
        changed_files=_changed_files(payload),
        session_id=_optional_string(payload.get("session_id")),
        warnings=(),
    )


def invalid_hook_payload_json(error: InvalidHookPayload) -> dict[str, JsonValue]:
    return {"status": "ERROR", "error_code": error.error_code, "message": error.message}


def _read_stdin(stdin: TextIO) -> str:
    if stdin.isatty():
        return ""
    return stdin.read().strip()


def _event_name(payload: dict[str, JsonValue], fallback: str) -> str:
    raw = payload.get("hook_event_name")
    if isinstance(raw, str) and raw.strip():
        return raw
    return fallback


def _changed_files(value: JsonValue) -> tuple[str, ...]:
    files: list[str] = []
    _collect_changed_files(value, files)
    seen: set[str] = set()
    normalized: list[str] = []
    for file_path in files:
        item = file_path.strip().replace("\\", "/")
        if item and item not in seen:
            seen.add(item)
            normalized.append(item)
    return tuple(normalized)


def _collect_changed_files(value: JsonValue, files: list[str]) -> None:
    match value:
        case dict() as mapping:
            for key, item in mapping.items():
                if key in FILE_KEYS:
                    _collect_file_value(item, files)
                else:
                    _collect_changed_files(item, files)
        case list() as values:
            for item in values:
                _collect_changed_files(item, files)
        case bool() | int() | float() | str() | None:
            return


def _collect_file_value(value: JsonValue, files: list[str]) -> None:
    match value:
        case str() as file_path:
            files.append(file_path)
        case list() as values:
            for item in values:
                _collect_file_value(item, files)
        case dict() as mapping:
            for item in mapping.values():
                _collect_file_value(item, files)
        case bool() | int() | float() | None:
            return


def _optional_string(value: JsonValue | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None
