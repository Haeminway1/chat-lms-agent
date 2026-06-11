from __future__ import annotations

import json
import locale
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, BinaryIO, Final, TextIO, cast

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

FILE_KEYS: Final = frozenset({"changed_files", "changedFiles", "file_path", "filePath"})
MAX_HOOK_STDIN_BYTES: Final = 1_048_576


@dataclass(frozen=True, slots=True)
class HookPayload:
    event_name: str
    changed_files: tuple[str, ...]
    session_id: str | None
    prompt: str | None
    warnings: tuple[str, ...]
    stop_hook_active: bool = False
    source: str | None = None
    trigger: str | None = None
    tool_name: str | None = None
    tool_input: JsonValue | None = None


@dataclass(frozen=True, slots=True)
class InvalidHookPayload:
    error_code: str
    message: str


type HookPayloadResult = HookPayload | InvalidHookPayload


def read_hook_payload(stdin: TextIO, *, event_name: str) -> HookPayloadResult:
    raw = _read_stdin(stdin)
    if raw is None:
        return InvalidHookPayload(
            error_code="INVALID_HOOK_PAYLOAD",
            message="hook stdin payload too large",
        )
    if raw == "":
        return HookPayload(
            event_name=event_name,
            changed_files=(),
            session_id=None,
            prompt=None,
            warnings=(),
        )
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
        prompt=_prompt_text(payload),
        warnings=(),
        stop_hook_active=payload.get("stop_hook_active") is True
        or payload.get("stopHookActive") is True,
        source=_optional_string(payload.get("source")),
        trigger=_optional_string(payload.get("trigger")),
        tool_name=_first_string(payload, ("tool_name", "toolName")),
        tool_input=_tool_input(payload),
    )


def invalid_hook_payload_json(error: InvalidHookPayload) -> dict[str, JsonValue]:
    return {"status": "ERROR", "error_code": error.error_code, "message": error.message}


def _read_stdin(stdin: TextIO) -> str | None:
    """Read bounded stdin; ``None`` means the payload exceeded the ingress cap.

    Hosts write UTF-8 regardless of the console codepage (Korean Windows
    defaults to cp949), so the byte stream is decoded UTF-8 first with a
    locale fallback for legacy pipes.
    """
    if stdin.isatty():
        return ""
    buffer = cast("BinaryIO | None", getattr(stdin, "buffer", None))
    if buffer is not None:
        raw_bytes = buffer.read(MAX_HOOK_STDIN_BYTES + 1)
        if len(raw_bytes) > MAX_HOOK_STDIN_BYTES:
            return None
        try:
            return raw_bytes.decode("utf-8-sig").strip()
        except UnicodeDecodeError:
            fallback = locale.getpreferredencoding(do_setlocale=False)
            return raw_bytes.decode(fallback, errors="replace").strip()
    raw = stdin.read(MAX_HOOK_STDIN_BYTES + 1)
    if len(raw) > MAX_HOOK_STDIN_BYTES:
        return None
    return raw.strip()


def _event_name(payload: dict[str, JsonValue], fallback: str) -> str:
    # "hook_event_name" is the host dialect; "event_type" is harness-event-v1.
    for key in ("hook_event_name", "event_type"):
        raw = payload.get(key)
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


def _prompt_text(payload: dict[str, JsonValue]) -> str | None:
    for key in ("prompt", "user_prompt", "userPrompt", "message", "input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _first_string(payload: dict[str, JsonValue], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _optional_string(payload.get(key))
        if value is not None:
            return value
    return None


def _tool_input(payload: dict[str, JsonValue]) -> JsonValue | None:
    for key in ("tool_input", "toolInput"):
        if key in payload:
            return payload[key]
    return None
