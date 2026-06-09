from __future__ import annotations

import hashlib
import json
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.state import STATE_DIR, JsonValue, ProfileState

if TYPE_CHECKING:
    from pathlib import Path

VALID_EVIDENCE_MARKERS: Final = (
    "pytest",
    "exit_code: 0",
    "manual qa",
    "tmux",
    "trace_",
    "audit_",
    "approval_",
    "qa-evidence",
)


def goal_status(profile: ProfileState) -> dict[str, JsonValue]:
    payload = _load_goals(profile)
    goals = payload.get("goals")
    if not isinstance(goals, dict):
        goals = _default_goals()
        _save_goals(profile, {"goals": goals})
    return {
        "status": "PASS",
        "schema_version": "goal-ledger-v1",
        "goals": goals,
    }


def add_goal_evidence(
    profile: ProfileState,
    goal_id: str,
    source_path: Path,
) -> tuple[int, dict[str, JsonValue]]:
    try:
        content = source_path.read_text(encoding="utf-8")
    except OSError:
        return 2, {"status": "ERROR", "error_code": "GOAL_EVIDENCE_NOT_FOUND"}
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    evidence_id = f"evidence_{digest[:16]}"
    evidence_dir = _goal_dir(profile) / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    _ = (evidence_dir / f"{evidence_id}.txt").write_text(content, encoding="utf-8")
    payload = _load_goals(profile)
    goals = payload.get("goals")
    if not isinstance(goals, dict):
        goals = _default_goals()
    goal = goals.get(goal_id)
    if not isinstance(goal, dict):
        goal = _default_goal(goal_id)
    evidence_refs = goal.get("evidence_refs")
    if not isinstance(evidence_refs, list):
        evidence_refs = []
    if evidence_id not in evidence_refs:
        evidence_refs.append(evidence_id)
    goal["evidence_refs"] = evidence_refs
    goal["qa_verifier_status"] = "PENDING"
    goals[goal_id] = goal
    _save_goals(profile, {"goals": goals})
    return (
        0,
        {
            "status": "PASS",
            "goal_id": goal_id,
            "evidence_id": evidence_id,
            "sha256": digest,
            "bytes_count": len(content.encode("utf-8")),
        },
    )


def verify_goal(profile: ProfileState, goal_id: str) -> tuple[int, dict[str, JsonValue]]:
    payload = _load_goals(profile)
    goals = payload.get("goals")
    goal = goals.get(goal_id) if isinstance(goals, dict) else None
    if not isinstance(goal, dict):
        goal = _default_goal(goal_id)
    evidence_refs = goal.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        return (
            5,
            {
                "status": "BLOCKED",
                "error_code": "GOAL_EVIDENCE_MISSING",
                "schema_version": "goal-ledger-v1",
                "goal_id": goal_id,
                "qa_verifier_status": "BLOCKED",
                "missing": ["evidence_refs"],
            },
        )
    valid_evidence_refs = _valid_evidence_refs(profile, evidence_refs)
    valid_evidence_values: list[JsonValue] = list(valid_evidence_refs)
    if not valid_evidence_refs:
        goal["qa_verifier_status"] = "BLOCKED"
        if isinstance(goals, dict):
            goals[goal_id] = goal
            _save_goals(profile, {"goals": goals})
        return (
            5,
            {
                "status": "BLOCKED",
                "error_code": "VALID_EVIDENCE_REQUIRED",
                "schema_version": "goal-ledger-v1",
                "goal_id": goal_id,
                "qa_verifier_status": "BLOCKED",
                "evidence_refs": evidence_refs,
                "valid_evidence_refs": [],
            },
        )
    goal["qa_verifier_status"] = "PASS"
    if isinstance(goals, dict):
        goals[goal_id] = goal
        _save_goals(profile, {"goals": goals})
    return (
        0,
        {
            "status": "PASS",
            "schema_version": "goal-ledger-v1",
            "goal_id": goal_id,
            "qa_verifier_status": "PASS",
            "evidence_refs": evidence_refs,
            "valid_evidence_refs": valid_evidence_values,
        },
    )


def _default_goal(goal_id: str = "goal_default") -> dict[str, JsonValue]:
    return {
        "goal_id": goal_id,
        "objective": "Chat LMS Agent harness work",
        "subgoals": [],
        "evidence_refs": [],
        "blockers": [],
        "approval_refs": [],
        "trace_refs": [],
        "qa_verifier_status": "PENDING",
        "next_action": "add evidence then verify",
    }


def _default_goals() -> dict[str, JsonValue]:
    return {"goal_default": _default_goal()}


def _valid_evidence_refs(profile: ProfileState, evidence_refs: list[JsonValue]) -> list[str]:
    valid_refs: list[str] = []
    for evidence_ref in evidence_refs:
        if not isinstance(evidence_ref, str):
            continue
        content = _read_evidence(profile, evidence_ref)
        if content is not None and _is_valid_evidence(content):
            valid_refs.append(evidence_ref)
    return valid_refs


def _read_evidence(profile: ProfileState, evidence_id: str) -> str | None:
    path = _goal_dir(profile) / "evidence" / f"{evidence_id}.txt"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _is_valid_evidence(content: str) -> bool:
    lowered = content.lower()
    return any(marker in lowered for marker in VALID_EVIDENCE_MARKERS)


def _goal_dir(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / "goals"


def _goal_path(profile: ProfileState) -> Path:
    return _goal_dir(profile) / "goals.json"


def _load_goals(profile: ProfileState) -> dict[str, JsonValue]:
    path = _goal_path(profile)
    if not path.exists():
        return {}
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _save_goals(profile: ProfileState, payload: dict[str, JsonValue]) -> None:
    path = _goal_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    _ = tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)
