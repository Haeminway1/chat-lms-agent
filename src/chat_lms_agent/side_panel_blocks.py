"""Side-panel block lifecycle: draft -> registered -> active -> deprecated.

The runtime extension path for building blocks (V5 Track A). Drafts live in
profile-state quarantine and never reach the production catalog; promotion
requires test evidence, a ``panel:<id>`` memory record, and a consumable
teacher approval. Terminal transitions require a closing report (oh-my-pi
yield-guard trait): unfinished block work is never silently abandoned.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, Literal, NotRequired, TypedDict, cast

from chat_lms_agent.approvals import (
    approval_id_for,
    approval_is_approved,
    approval_is_denied,
    consume_approval,
    ensure_approval_request,
)
from chat_lms_agent.state import (
    STATE_DIR,
    ProfileState,
    load_memory,
    read_state_mapping,
    redact_text,
    write_state_mapping,
)

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

type BlockLifecycleState = Literal["draft", "registered", "active", "deprecated"]

BLOCK_LIFECYCLE_FILE: Final = "block-lifecycle.json"
BLOCK_DRAFTS_DIR: Final = "side-panel-drafts"
BLOCK_PRIVACY_LEVELS: Final = frozenset(
    {"workspace", "profile", "class", "learner", "tool", "schema", "side_panel"},
)
ALLOWED_BLOCK_TRANSITIONS: Final[dict[str, frozenset[str]]] = {
    "draft": frozenset({"registered", "deprecated"}),
    "registered": frozenset({"active", "deprecated"}),
    "active": frozenset({"deprecated"}),
    "deprecated": frozenset(),
}


class BlockRecord(TypedDict):
    id: str
    label: str
    summary: str
    render_contract: dict[str, JsonValue]
    privacy_level: str
    action_safety: dict[str, JsonValue]
    test_contract: dict[str, JsonValue]
    reuse_review: dict[str, JsonValue]
    lifecycle_state: BlockLifecycleState
    evidence_ref: NotRequired[str]
    closing_report: NotRequired[str]


def scaffold_block(profile: ProfileState, proposal_path: Path) -> tuple[int, dict[str, JsonValue]]:
    proposal = _read_json_object(proposal_path)
    if proposal is None:
        invalid: list[JsonValue] = ["INVALID_JSON"]
        return 2, {
            "status": "ERROR",
            "error_code": "INVALID_BLOCK_PROPOSAL",
            "errors": invalid,
        }
    errors = _proposal_errors(proposal)
    if errors:
        error_values: list[JsonValue] = []
        error_values.extend(errors)
        return 2, {
            "status": "ERROR",
            "error_code": "INVALID_BLOCK_PROPOSAL",
            "errors": error_values,
        }
    record = _record_from_proposal(proposal)
    records = _load_block_records(profile)
    records[record["id"]] = record
    _write_block_records(profile, records)
    quarantine = _quarantine_dir(profile, record["id"])
    quarantine.mkdir(parents=True, exist_ok=True)
    _ = (quarantine / "proposal.json").write_text(
        json.dumps(_record_json(record), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # The approval request is created lazily at the first promote attempt so
    # an untouched draft never blocks session closeout.
    return 0, {
        "status": "PASS",
        "block_id": record["id"],
        "lifecycle_state": record["lifecycle_state"],
        "quarantine": f"<profile-root>/{STATE_DIR}/{BLOCK_DRAFTS_DIR}/{record['id']}",
        "approval_id": approval_id_for(_plan_id(record["id"])),
        "promote_requires": ["--evidence", f"memory key panel:{record['id']}", "teacher approval"],
    }


def set_block_state(
    profile: ProfileState,
    block_id: str,
    state: BlockLifecycleState,
    *,
    evidence: str | None = None,
    report: str | None = None,
) -> tuple[int, dict[str, JsonValue]]:
    records = _load_block_records(profile)
    record = records.get(block_id)
    if record is None:
        return 2, {"status": "ERROR", "error_code": "UNKNOWN_BLOCK", "block_id": block_id}
    current = record["lifecycle_state"]
    if state not in ALLOWED_BLOCK_TRANSITIONS[current]:
        return 2, {
            "status": "ERROR",
            "error_code": "INVALID_LIFECYCLE_TRANSITION",
            "block_id": block_id,
            "from_state": current,
            "to_state": state,
        }
    if state == "deprecated":
        if report is None or not report.strip():
            return 2, {
                "status": "ERROR",
                "error_code": "MISSING_CLOSING_REPORT",
                "block_id": block_id,
                "message": "deprecate requires --report (what was tried, verdict, evidence)",
            }
        record["closing_report"] = redact_text(report)
    if state == "active":
        gate_code, gate_payload = _promote_gate(profile, record, evidence)
        if gate_payload is not None:
            return gate_code, gate_payload
        consume_approval(profile, approval_id_for(_plan_id(block_id)), _plan_id(block_id))
    record["lifecycle_state"] = state
    _write_block_records(profile, records)
    return 0, {
        "status": "PASS",
        "block_id": block_id,
        "lifecycle_state": record["lifecycle_state"],
    }


def explain_block(profile: ProfileState, block_id: str) -> tuple[int, dict[str, JsonValue]]:
    record = _load_block_records(profile).get(block_id)
    if record is None:
        return 2, {"status": "ERROR", "error_code": "UNKNOWN_BLOCK", "block_id": block_id}
    return 0, {"status": "PASS", "block": _record_json(record)}


def preview_block(
    profile: ProfileState,
    block_id: str,
    sample_path: Path,
) -> tuple[int, dict[str, JsonValue]]:
    record = _load_block_records(profile).get(block_id)
    if record is None:
        return 2, {"status": "ERROR", "error_code": "UNKNOWN_BLOCK", "block_id": block_id}
    sample = _read_json_object(sample_path)
    if sample is None:
        invalid: list[JsonValue] = ["INVALID_JSON"]
        return 2, {"status": "ERROR", "error_code": "INVALID_SAMPLE", "errors": invalid}
    errors: list[JsonValue] = []
    required = record["render_contract"].get("required_keys")
    if isinstance(required, list):
        errors.extend(
            f"missing required key: {key}"
            for key in required
            if isinstance(key, str) and key not in sample
        )
    if record["privacy_level"] not in BLOCK_PRIVACY_LEVELS:
        errors.append(f"unknown privacy_level: {record['privacy_level']}")
    if errors:
        return 2, {"status": "ERROR", "error_code": "PREVIEW_FAILED", "errors": errors}
    previewed: list[JsonValue] = []
    previewed.extend(sorted(sample))
    return 0, {
        "status": "PASS",
        "block_id": block_id,
        "privacy_level": record["privacy_level"],
        "previewed_keys": previewed,
    }


def active_profile_blocks(profile: ProfileState) -> list[JsonValue]:
    return [
        _record_json(record)
        for record in _load_block_records(profile).values()
        if record["lifecycle_state"] == "active"
    ]


def open_block_ids(profile: ProfileState) -> list[str]:
    return sorted(
        record["id"]
        for record in _load_block_records(profile).values()
        if record["lifecycle_state"] in {"draft", "registered"}
    )


def _promote_gate(
    profile: ProfileState,
    record: BlockRecord,
    evidence: str | None,
) -> tuple[int, dict[str, JsonValue] | None]:
    block_id = record["id"]
    if evidence is None or not evidence.strip():
        return 2, {
            "status": "ERROR",
            "error_code": "MISSING_PROMOTE_EVIDENCE",
            "block_id": block_id,
        }
    plan_id = _plan_id(block_id)
    approval_id = approval_id_for(plan_id)
    _ = ensure_approval_request(
        profile,
        plan_id=plan_id,
        operation="side-panel block promote",
    )
    if approval_is_denied(profile, approval_id, plan_id):
        return 2, {
            "status": "ERROR",
            "error_code": "APPROVAL_DENIED",
            "block_id": block_id,
            "approval_id": approval_id,
        }
    if not approval_is_approved(profile, approval_id, plan_id):
        return 3, {
            "status": "NEEDS_APPROVAL",
            "block_id": block_id,
            "approval_id": approval_id,
            "message_ko": "교사 승인 후 다시 promote 하세요.",
        }
    required_key = f"panel:{block_id}"
    memory_keys = {entry["key"] for entry in load_memory(profile)}
    if required_key not in memory_keys:
        return 5, {
            "status": "BLOCKED",
            "error_code": "MEMORY_UPDATE_REQUIRED",
            "block_id": block_id,
            "required_key": required_key,
        }
    record["evidence_ref"] = redact_text(evidence)
    return 0, None


def _proposal_errors(proposal: dict[str, JsonValue]) -> list[str]:
    errors: list[str] = []
    if not _non_empty_string(proposal.get("id")):
        errors.append("MISSING_ID")
    if not _non_empty_string(proposal.get("summary")):
        errors.append("MISSING_SUMMARY")
    if not isinstance(proposal.get("render_contract"), dict):
        errors.append("MISSING_RENDER_CONTRACT")
    if proposal.get("privacy_level") not in BLOCK_PRIVACY_LEVELS:
        errors.append("INVALID_PRIVACY_LEVEL")
    safety = proposal.get("action_safety")
    if not (
        isinstance(safety, dict)
        and isinstance(safety.get("requires_approval"), bool)
        and isinstance(safety.get("dry_run_default"), bool)
    ):
        errors.append("MISSING_ACTION_SAFETY")
    if not isinstance(proposal.get("test_contract"), dict):
        errors.append("MISSING_TEST_CONTRACT")
    if not isinstance(proposal.get("reuse_review"), dict):
        errors.append("MISSING_REUSE_REVIEW")
    return errors


def _record_from_proposal(proposal: dict[str, JsonValue]) -> BlockRecord:
    block_id = proposal["id"]
    label = proposal.get("label")
    summary = proposal["summary"]
    privacy = proposal["privacy_level"]
    return {
        "id": block_id if isinstance(block_id, str) else "",
        "label": label if isinstance(label, str) else str(block_id),
        "summary": redact_text(summary) if isinstance(summary, str) else "",
        "render_contract": _json_object(proposal.get("render_contract")),
        "privacy_level": privacy if isinstance(privacy, str) else "",
        "action_safety": _json_object(proposal.get("action_safety")),
        "test_contract": _json_object(proposal.get("test_contract")),
        "reuse_review": _json_object(proposal.get("reuse_review")),
        "lifecycle_state": "draft",
    }


def _record_json(record: BlockRecord) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "id": record["id"],
        "label": record["label"],
        "summary": record["summary"],
        "render_contract": record["render_contract"],
        "privacy_level": record["privacy_level"],
        "action_safety": record["action_safety"],
        "test_contract": record["test_contract"],
        "reuse_review": record["reuse_review"],
        "lifecycle_state": record["lifecycle_state"],
        "source": "profile",
    }
    evidence_ref = record.get("evidence_ref")
    if evidence_ref is not None:
        payload["evidence_ref"] = evidence_ref
    closing_report = record.get("closing_report")
    if closing_report is not None:
        payload["closing_report"] = closing_report
    return payload


def _load_block_records(profile: ProfileState) -> dict[str, BlockRecord]:
    payload = read_state_mapping(profile, BLOCK_LIFECYCLE_FILE)
    raw_blocks = payload.get("blocks", {})
    if not isinstance(raw_blocks, dict):
        return {}
    records: dict[str, BlockRecord] = {}
    for block_id, item in raw_blocks.items():
        if isinstance(item, dict):
            record = _parse_record(item)
            if record is not None:
                records[block_id] = record
    return records


def _write_block_records(profile: ProfileState, records: dict[str, BlockRecord]) -> None:
    blocks: dict[str, JsonValue] = {
        block_id: _record_json(record) for block_id, record in records.items()
    }
    write_state_mapping(profile, BLOCK_LIFECYCLE_FILE, {"blocks": blocks})


def _parse_record(item: dict[str, JsonValue]) -> BlockRecord | None:
    block_id = item.get("id")
    label = item.get("label")
    summary = item.get("summary")
    privacy = item.get("privacy_level")
    state = _parse_state(item.get("lifecycle_state"))
    if not (isinstance(block_id, str) and isinstance(label, str) and isinstance(summary, str)):
        return None
    if state is None or not isinstance(privacy, str):
        return None
    record: BlockRecord = {
        "id": block_id,
        "label": label,
        "summary": summary,
        "render_contract": _json_object(item.get("render_contract")),
        "privacy_level": privacy,
        "action_safety": _json_object(item.get("action_safety")),
        "test_contract": _json_object(item.get("test_contract")),
        "reuse_review": _json_object(item.get("reuse_review")),
        "lifecycle_state": state,
    }
    evidence_ref = item.get("evidence_ref")
    if isinstance(evidence_ref, str) and evidence_ref:
        record["evidence_ref"] = evidence_ref
    closing_report = item.get("closing_report")
    if isinstance(closing_report, str) and closing_report:
        record["closing_report"] = closing_report
    return record


def _parse_state(value: JsonValue | None) -> BlockLifecycleState | None:
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


def _plan_id(block_id: str) -> str:
    return f"side-panel-block-{block_id}"


def _quarantine_dir(profile: ProfileState, block_id: str) -> Path:
    return profile.root / STATE_DIR / BLOCK_DRAFTS_DIR / block_id


def _read_json_object(path: Path) -> dict[str, JsonValue] | None:
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
