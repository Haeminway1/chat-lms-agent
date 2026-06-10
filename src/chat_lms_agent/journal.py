from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.state import STATE_DIR, JsonValue, ProfileState, redact_text

if TYPE_CHECKING:
    from pathlib import Path

TRACE_SCHEMA_VERSION: Final = "trace-v1"
AUDIT_SCHEMA_VERSION: Final = "audit-v1"


@dataclass(frozen=True, slots=True)
class _RecordShape:
    schema_version: str
    record_id_key: str
    record_id: str
    kind_key: str
    kind: str


def trace_context(profile: ProfileState | None) -> dict[str, JsonValue]:
    # No live counts here: counts change every record and would re-key the
    # injected payload on each hook event (prompt-cache hostile, O(n) scan).
    _ = profile
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "storage": "<profile-root>/.chat-lms-state/trace",
        "list_command": "python -m chat_lms_agent trace list --profile-root <root> --json",
    }


def audit_context(profile: ProfileState | None) -> dict[str, JsonValue]:
    _ = profile
    return {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "storage": "<profile-root>/.chat-lms-state/audit",
        "list_command": "python -m chat_lms_agent audit list --profile-root <root> --json",
    }


def write_trace(
    profile: ProfileState,
    event_type: str,
    summary: str,
    details: dict[str, JsonValue] | None = None,
) -> str:
    trace_id = _record_id("trace", event_type)
    payload = _record_payload(
        profile,
        _RecordShape(TRACE_SCHEMA_VERSION, "trace_id", trace_id, "event_type", event_type),
        summary=summary,
        details=details,
    )
    _write_json(_trace_dir(profile) / f"{trace_id}.json", payload)
    return trace_id


def write_audit(
    profile: ProfileState,
    operation: str,
    summary: str,
    details: dict[str, JsonValue] | None = None,
) -> str:
    audit_id = _record_id("audit", operation)
    payload = _record_payload(
        profile,
        _RecordShape(AUDIT_SCHEMA_VERSION, "audit_id", audit_id, "operation", operation),
        summary=summary,
        details=details,
    )
    _write_json(_audit_dir(profile) / f"{audit_id}.json", payload)
    return audit_id


def trace_refs(profile: ProfileState) -> list[str]:
    return _refs_from_dir(_trace_dir(profile), "trace_id")


def audit_refs(profile: ProfileState) -> list[str]:
    return _refs_from_dir(_audit_dir(profile), "audit_id")


def list_trace_records(profile: ProfileState) -> dict[str, JsonValue]:
    records: list[JsonValue] = []
    records.extend(_records_from_dir(profile, _trace_dir(profile)))
    return {
        "status": "PASS",
        "schema_version": TRACE_SCHEMA_VERSION,
        "traces": records,
    }


def show_trace_record(profile: ProfileState, trace_id: str) -> tuple[int, dict[str, JsonValue]]:
    for record in _records_from_dir(profile, _trace_dir(profile)):
        if record.get("trace_id") == trace_id:
            payload: dict[str, JsonValue] = {
                "status": "PASS",
                "schema_version": TRACE_SCHEMA_VERSION,
                "trace": record,
            }
            return 0, payload
    return 2, {"status": "ERROR", "error_code": "TRACE_NOT_FOUND"}


def export_trace_trajectory(profile: ProfileState) -> dict[str, JsonValue]:
    trajectory: list[JsonValue] = [
        _trajectory_item(record) for record in _records_from_dir(profile, _trace_dir(profile))
    ]
    return {
        "status": "PASS",
        "schema_version": "trajectory-v1",
        "profile_root": "<profile-root>",
        "trajectory": trajectory,
    }


def inspect_trace_trajectory(
    profile: ProfileState,
    trace_id: str,
) -> tuple[int, dict[str, JsonValue]]:
    for record in _records_from_dir(profile, _trace_dir(profile)):
        if record.get("trace_id") == trace_id:
            return (
                0,
                {
                    "status": "PASS",
                    "schema_version": "trajectory-v1",
                    "trajectory": _trajectory_item(record),
                },
            )
    return 2, {"status": "ERROR", "error_code": "TRACE_NOT_FOUND"}


def list_audit_records(profile: ProfileState) -> dict[str, JsonValue]:
    records: list[JsonValue] = []
    records.extend(_records_from_dir(profile, _audit_dir(profile)))
    return {
        "status": "PASS",
        "schema_version": AUDIT_SCHEMA_VERSION,
        "audits": records,
    }


def redact_runtime_text(profile: ProfileState, value: str) -> str:
    redacted = redact_text(value)
    replacements = {
        str(profile.root): "<profile-root>",
        profile.root.as_posix(): "<profile-root>",
        str(profile.repo_root): "<repo-root>",
        profile.repo_root.as_posix(): "<repo-root>",
    }
    for needle, label in replacements.items():
        redacted = redacted.replace(needle, label)
    return re.sub(r"(?i)raw stdout:[^\n\r]*", "[redacted]", redacted)


def redact_runtime_value(profile: ProfileState, value: JsonValue) -> JsonValue:
    if isinstance(value, str):
        return redact_runtime_text(profile, value)
    if isinstance(value, list):
        return [redact_runtime_value(profile, item) for item in value]
    if isinstance(value, dict):
        return {key: redact_runtime_value(profile, item) for key, item in value.items()}
    return value


def _record_payload(
    profile: ProfileState,
    shape: _RecordShape,
    *,
    summary: str,
    details: dict[str, JsonValue] | None,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "schema_version": shape.schema_version,
        shape.record_id_key: shape.record_id,
        shape.kind_key: shape.kind,
        "profile_root": "<profile-root>",
        "summary": redact_runtime_text(profile, summary),
    }
    if details is not None:
        payload["details"] = redact_runtime_value(profile, details)
    return payload


def _trajectory_item(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    trace_id = record.get("trace_id")
    event_type = record.get("event_type")
    summary = record.get("summary")
    details = record.get("details")
    command: JsonValue = None
    if isinstance(details, dict):
        command = details.get("command")
    return {
        "trace_id": trace_id if isinstance(trace_id, str) else "",
        "event_type": event_type if isinstance(event_type, str) else "",
        "summary": summary if isinstance(summary, str) else "",
        "command": command,
        "approval_checkpoint": "unknown",
        "memory_effects": [],
        "audit_effects": [],
        "next_session_obligations": [],
    }


def _refs_from_dir(path: Path, key: str) -> list[str]:
    refs: list[str] = []
    if not path.exists():
        return refs
    for json_path in sorted(path.glob("*.json")):
        payload = _read_json_object(json_path)
        value = payload.get(key) if payload is not None else None
        if isinstance(value, str):
            refs.append(value)
    for jsonl_path in sorted(path.glob("*.jsonl")):
        refs.extend(_refs_from_jsonl(jsonl_path, key))
    return refs


def _records_from_dir(profile: ProfileState, path: Path) -> list[dict[str, JsonValue]]:
    records: list[dict[str, JsonValue]] = []
    if not path.exists():
        return records
    for json_path in sorted(path.glob("*.json")):
        payload = _read_json_object(json_path)
        if payload is not None:
            records.append(_redacted_record(profile, payload))
    for jsonl_path in sorted(path.glob("*.jsonl")):
        records.extend(
            _redacted_record(profile, record) for record in _records_from_jsonl(jsonl_path)
        )
    return records


def _redacted_record(
    profile: ProfileState,
    record: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    redacted = redact_runtime_value(profile, record)
    if isinstance(redacted, dict):
        return redacted
    return {}


def _refs_from_jsonl(path: Path, key: str) -> list[str]:
    refs: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return refs
    for line in lines:
        try:
            payload = cast("JsonValue", json.loads(line))
        except JSONDecodeError:
            continue
        if isinstance(payload, dict):
            value = payload.get(key)
            if isinstance(value, str):
                refs.append(value)
    return refs


def _records_from_jsonl(path: Path) -> list[dict[str, JsonValue]]:
    records: list[dict[str, JsonValue]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return records
    for line in lines:
        try:
            payload = cast("JsonValue", json.loads(line))
        except JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _read_json_object(path: Path) -> dict[str, JsonValue] | None:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _record_id(prefix: str, value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    if not slug:
        slug = "event"
    return f"{prefix}_{slug}_{time.time_ns()}"


def _trace_dir(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / "trace"


def _audit_dir(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / "audit"


def _write_json(path: Path, payload: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    _ = tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)
