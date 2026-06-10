from __future__ import annotations

import json
import re
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from pathlib import Path

from chat_lms_agent.state import STATE_DIR, JsonValue, ProfileState

APPROVAL_SCHEMA_VERSION: Final = "approval-v1"
REQUEST_SCHEMA_VERSION: Final = "approval-request-v1"
AGENT_ACTOR: Final = "codex_desktop_agent"


def approval_context(profile: ProfileState | None) -> dict[str, JsonValue]:
    records = _load_records(profile) if profile is not None else []
    pending: list[JsonValue] = []
    pending.extend(_pending_ids(records))
    return {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "storage": "<profile-root>/.chat-lms-state/approvals/approvals.json",
        "pending": pending,
    }


def ensure_approval_request(
    profile: ProfileState,
    *,
    plan_id: str,
    operation: str,
) -> dict[str, JsonValue]:
    records = _load_records(profile)
    approval_id = approval_id_for(plan_id)
    for record in records:
        if record.get("approval_id") == approval_id:
            _save_records(profile, records)
            return _request_payload(record)
    record: dict[str, JsonValue] = {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_id": approval_id,
        "plan_id": plan_id,
        "operation": operation,
        "status": "planned",
        "requested_by": AGENT_ACTOR,
        "approved_by": None,
    }
    records.append(record)
    _save_records(profile, records)
    return _request_payload(record)


def approve_request(
    profile: ProfileState,
    approval_id: str,
    actor: str,
) -> tuple[int, dict[str, JsonValue]]:
    if actor == AGENT_ACTOR:
        return (
            2,
            {
                "status": "REJECTED",
                "error_code": "SELF_APPROVAL_REJECTED",
                "schema_version": APPROVAL_SCHEMA_VERSION,
            },
        )
    records = _load_records(profile)
    for record in records:
        if record.get("approval_id") == approval_id:
            error_code = _terminal_error_code(_approval_status(record))
            if error_code is not None:
                return (
                    2,
                    {
                        "status": "ERROR",
                        "error_code": error_code,
                        "approval_id": approval_id,
                    },
                )
            record["status"] = "approved"
            record["approved_by"] = actor
            _save_records(profile, records)
            return 0, _approval_payload(record)
    return 2, {"status": "ERROR", "error_code": "APPROVAL_NOT_FOUND"}


def deny_request(
    profile: ProfileState,
    approval_id: str,
    actor: str,
) -> tuple[int, dict[str, JsonValue]]:
    records = _load_records(profile)
    for record in records:
        if record.get("approval_id") == approval_id:
            record["status"] = "denied"
            record["approved_by"] = actor
            _save_records(profile, records)
            return 0, _approval_payload(record)
    return 2, {"status": "ERROR", "error_code": "APPROVAL_NOT_FOUND"}


def list_approvals(profile: ProfileState) -> dict[str, JsonValue]:
    return {
        "status": "PASS",
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approvals": [_public_record(record) for record in _load_records(profile)],
    }


def show_approval(profile: ProfileState, approval_id: str) -> tuple[int, dict[str, JsonValue]]:
    for record in _load_records(profile):
        if record.get("approval_id") == approval_id:
            return 0, {"status": "PASS", **_public_record(record)}
    return 2, {"status": "ERROR", "error_code": "APPROVAL_NOT_FOUND"}


def approval_is_approved(profile: ProfileState, approval_id: str, plan_id: str) -> bool:
    for record in _load_records(profile):
        if record.get("approval_id") == approval_id and record.get("plan_id") == plan_id:
            return _approval_status(record) == "APPROVED"
    return False


def approval_is_consumed(profile: ProfileState, approval_id: str, plan_id: str) -> bool:
    for record in _load_records(profile):
        if record.get("approval_id") == approval_id and record.get("plan_id") == plan_id:
            return _approval_status(record) == "CONSUMED"
    return False


def approval_is_denied(profile: ProfileState, approval_id: str, plan_id: str) -> bool:
    for record in _load_records(profile):
        if record.get("approval_id") == approval_id and record.get("plan_id") == plan_id:
            return _approval_status(record) == "DENIED"
    return False


def consume_approval(profile: ProfileState, approval_id: str, plan_id: str) -> None:
    records = _load_records(profile)
    for record in records:
        if record.get("approval_id") == approval_id and record.get("plan_id") == plan_id:
            record["status"] = "consumed"
    _save_records(profile, records)


def pending_approval_ids(profile: ProfileState) -> list[str]:
    return _pending_ids(_load_records(profile))


def has_unconsumed_approved(profile: ProfileState) -> bool:
    """Report whether at least one approval is APPROVED and not yet consumed."""
    return any(_approval_status(record) == "APPROVED" for record in _load_records(profile))


def approval_id_for(plan_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", plan_id).strip("_").lower()
    if not slug:
        slug = "request"
    return f"approval_{slug}"


def _request_payload(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    approval_id = record.get("approval_id")
    return {
        "status": "NEEDS_APPROVAL",
        "schema_version": REQUEST_SCHEMA_VERSION,
        "approval_id": approval_id if isinstance(approval_id, str) else "",
    }


def _approval_payload(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    approval_id = record.get("approval_id")
    return {
        "status": "PASS",
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_id": approval_id if isinstance(approval_id, str) else "",
        "approval_status": _approval_status(record),
    }


def _public_record(record: dict[str, JsonValue]) -> dict[str, JsonValue]:
    approval_id = record.get("approval_id")
    plan_id = record.get("plan_id")
    operation = record.get("operation")
    return {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_id": approval_id if isinstance(approval_id, str) else "",
        "plan_id": plan_id if isinstance(plan_id, str) else "",
        "operation": operation if isinstance(operation, str) else "",
        "approval_status": _approval_status(record),
    }


def _approval_status(record: dict[str, JsonValue]) -> str:
    status = record.get("status")
    if isinstance(status, str) and status.lower() == "approved":
        return "APPROVED"
    if isinstance(status, str) and status.lower() == "denied":
        return "DENIED"
    if isinstance(status, str) and status.lower() == "consumed":
        return "CONSUMED"
    return "PLANNED"


def _is_pending(record: dict[str, JsonValue]) -> bool:
    return _approval_status(record) == "PLANNED"


def _terminal_error_code(approval_status: str) -> str | None:
    if approval_status == "CONSUMED":
        return "APPROVAL_CONSUMED"
    if approval_status == "DENIED":
        return "APPROVAL_DENIED"
    return None


def _pending_ids(records: list[dict[str, JsonValue]]) -> list[str]:
    ids: list[str] = []
    for record in records:
        approval_id = record.get("approval_id")
        if isinstance(approval_id, str) and _is_pending(record):
            ids.append(approval_id)
    return ids


def _load_records(profile: ProfileState | None) -> list[dict[str, JsonValue]]:
    if profile is None:
        return []
    path = _approval_path(profile)
    if not path.exists():
        return []
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        return []
    if not isinstance(payload, dict):
        return []
    raw_records = payload.get("approvals")
    if not isinstance(raw_records, list):
        return []
    return [record for record in raw_records if isinstance(record, dict)]


def _save_records(profile: ProfileState, records: list[dict[str, JsonValue]]) -> None:
    path = _approval_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    _ = tmp_path.write_text(
        json.dumps({"approvals": records}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)


def _approval_path(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / "approvals" / "approvals.json"
