from __future__ import annotations

import json
import re
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.hosts import active_host

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

EVENT_SCHEMA_VERSION: Final = "harness-event-v1"


def normalize_event_file(path: Path) -> dict[str, JsonValue]:
    payload = _read_json_object(path)
    if payload is None:
        return {
            "status": "ERROR",
            "error_code": "INVALID_HARNESS_EVENT_PAYLOAD",
            "schema_version": EVENT_SCHEMA_VERSION,
        }
    source_event = _source_event_name(payload)
    return {
        "status": "PASS",
        "schema_version": EVENT_SCHEMA_VERSION,
        "host": _string(payload.get("host"), active_host().host_id),
        "event_type": _normalize_event_type(source_event),
        "source_event_name": source_event,
        "session_id": _string(payload.get("session_id"), ""),
    }


def harness_context_v3() -> dict[str, JsonValue]:
    future_hosts: list[JsonValue] = []
    future_hosts.extend(active_host().future_hosts)
    return {
        "schema_version": "harness-context-v3",
        "host_contract": "host-neutral-event-envelope",
        "current_host": active_host().host_id,
        "future_hosts": future_hosts,
        "event_command": (
            "python -m chat_lms_agent harness event normalize --from <event.json> --json"
        ),
    }


def _read_json_object(path: Path) -> dict[str, JsonValue] | None:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _source_event_name(payload: dict[str, JsonValue]) -> str:
    for key in ("hook_event_name", "event_name", "event_type"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return "unknown"


def _normalize_event_type(value: str) -> str:
    with_underscores = re.sub(r"(?<!^)(?=[A-Z])", "_", value).replace("-", "_")
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", with_underscores).strip("_").lower()
    if normalized:
        return normalized
    return "unknown"


def _string(value: JsonValue | None, default: str) -> str:
    if isinstance(value, str):
        return value
    return default
