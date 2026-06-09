from __future__ import annotations

import json
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, Literal, TypedDict, cast

from chat_lms_agent.state import STATE_DIR, JsonValue, ProfileState, redact_text

if TYPE_CHECKING:
    from pathlib import Path

LifecycleState = Literal["draft", "registered", "active", "deprecated"]
LIFECYCLE_FILE: Final = "agent-tool-lifecycle.json"
REQUIRED_CONTRACTS: Final = (
    ("command_contract", "MISSING_COMMAND_CONTRACT"),
    ("memory_obligation", "MISSING_MEMORY_OBLIGATION"),
    ("safety_boundary", "MISSING_SAFETY_BOUNDARY"),
    ("test_contract", "MISSING_TEST_CONTRACT"),
)


class AgentToolLifecycleRecord(TypedDict):
    id: str
    label: str
    summary: str
    command_contract: dict[str, JsonValue]
    memory_obligation: dict[str, JsonValue]
    safety_boundary: dict[str, JsonValue]
    test_contract: dict[str, JsonValue]
    lifecycle_state: LifecycleState


def scaffold_tool(profile: ProfileState, proposal_path: Path) -> dict[str, JsonValue]:
    proposal = _read_proposal(proposal_path)
    if proposal is None:
        return _invalid_payload(None, ("INVALID_JSON",))
    errors = _proposal_errors(proposal)
    if errors:
        return _invalid_payload(proposal, errors)
    record = _record_from_proposal(proposal, "draft")
    _save_record(profile, record)
    return _state_payload(record)


def set_lifecycle_state(
    profile: ProfileState,
    tool_id: str,
    state: LifecycleState,
) -> dict[str, JsonValue]:
    records = _load_records(profile)
    record = records.get(tool_id)
    if record is None:
        return {"status": "ERROR", "error_code": "UNKNOWN_AGENT_TOOL", "tool_id": tool_id}
    record["lifecycle_state"] = state
    _write_records(profile, records)
    return _state_payload(record)


def explain_tool(profile: ProfileState, tool_id: str) -> dict[str, JsonValue]:
    record = _load_records(profile).get(tool_id)
    if record is None:
        return {"status": "ERROR", "error_code": "UNKNOWN_AGENT_TOOL", "tool_id": tool_id}
    return {"status": "PASS", "tool": _record_json(record)}


def lifecycle_doctor(profile: ProfileState) -> dict[str, JsonValue]:
    records = _load_records(profile)
    return {
        "status": "PASS",
        "tool_count": len(records),
        "states": {tool_id: record["lifecycle_state"] for tool_id, record in records.items()},
    }


def _invalid_payload(
    proposal: dict[str, JsonValue] | None,
    errors: tuple[str, ...],
) -> dict[str, JsonValue]:
    proposal_id = proposal.get("id") if proposal is not None else None
    return {
        "status": "ERROR",
        "error_code": "INVALID_TOOL_PROPOSAL",
        "proposal_id": proposal_id if isinstance(proposal_id, str) else None,
        "errors": list(errors),
    }


def _proposal_errors(proposal: dict[str, JsonValue]) -> tuple[str, ...]:
    errors: list[str] = []
    if not _non_empty_string(proposal.get("id")):
        errors.append("MISSING_ID")
    if not _non_empty_string(proposal.get("summary")):
        errors.append("MISSING_SUMMARY")
    for key, error_code in REQUIRED_CONTRACTS:
        if not isinstance(proposal.get(key), dict):
            errors.append(error_code)
    return tuple(errors)


def _record_from_proposal(
    proposal: dict[str, JsonValue],
    state: LifecycleState,
) -> AgentToolLifecycleRecord:
    tool_id = proposal["id"]
    summary = proposal["summary"]
    label = proposal.get("label")
    return {
        "id": tool_id if isinstance(tool_id, str) else "",
        "label": label if isinstance(label, str) else str(tool_id),
        "summary": redact_text(summary) if isinstance(summary, str) else "",
        "command_contract": _json_object(proposal["command_contract"]),
        "memory_obligation": _json_object(proposal["memory_obligation"]),
        "safety_boundary": _json_object(proposal["safety_boundary"]),
        "test_contract": _json_object(proposal["test_contract"]),
        "lifecycle_state": state,
    }


def _state_payload(record: AgentToolLifecycleRecord) -> dict[str, JsonValue]:
    return {
        "status": "PASS",
        "tool_id": record["id"],
        "lifecycle_state": record["lifecycle_state"],
    }


def _record_json(record: AgentToolLifecycleRecord) -> dict[str, JsonValue]:
    return {
        "id": record["id"],
        "label": record["label"],
        "summary": record["summary"],
        "command_contract": record["command_contract"],
        "memory_obligation": record["memory_obligation"],
        "safety_boundary": record["safety_boundary"],
        "test_contract": record["test_contract"],
        "lifecycle_state": record["lifecycle_state"],
    }


def _save_record(profile: ProfileState, record: AgentToolLifecycleRecord) -> None:
    records = _load_records(profile)
    records[record["id"]] = record
    _write_records(profile, records)


def _load_records(profile: ProfileState) -> dict[str, AgentToolLifecycleRecord]:
    path = _lifecycle_path(profile)
    if not path.exists():
        return {}
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    raw_tools = payload.get("tools", {})
    if not isinstance(raw_tools, dict):
        return {}
    records: dict[str, AgentToolLifecycleRecord] = {}
    for tool_id, item in raw_tools.items():
        if isinstance(item, dict):
            record = _parse_record(item)
            if record is not None:
                records[tool_id] = record
    return records


def _write_records(profile: ProfileState, records: dict[str, AgentToolLifecycleRecord]) -> None:
    payload: dict[str, JsonValue] = {
        "tools": {tool_id: _record_json(record) for tool_id, record in records.items()},
    }
    path = _lifecycle_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    _ = tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)


def _parse_record(item: dict[str, JsonValue]) -> AgentToolLifecycleRecord | None:
    tool_id = item.get("id")
    label = item.get("label")
    summary = item.get("summary")
    state = _parse_state(item.get("lifecycle_state"))
    if not (isinstance(tool_id, str) and isinstance(label, str) and isinstance(summary, str)):
        return None
    if state is None:
        return None
    return {
        "id": tool_id,
        "label": label,
        "summary": summary,
        "command_contract": _json_object(item.get("command_contract")),
        "memory_obligation": _json_object(item.get("memory_obligation")),
        "safety_boundary": _json_object(item.get("safety_boundary")),
        "test_contract": _json_object(item.get("test_contract")),
        "lifecycle_state": state,
    }


def _parse_state(value: JsonValue | None) -> LifecycleState | None:
    match value:
        case "draft":
            return "draft"
        case "registered":
            return "registered"
        case "active":
            return "active"
        case "deprecated":
            return "deprecated"
        case _:
            return None


def _lifecycle_path(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / LIFECYCLE_FILE


def _read_proposal(path: Path) -> dict[str, JsonValue] | None:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _json_object(value: JsonValue | None) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    return {}


def _non_empty_string(value: JsonValue | None) -> bool:
    return isinstance(value, str) and bool(value.strip())
