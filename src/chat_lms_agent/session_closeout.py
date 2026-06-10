from __future__ import annotations

from typing import Final

from chat_lms_agent.academy_db import store_path
from chat_lms_agent.academy_db_imports import unapplied_import_plan_ids
from chat_lms_agent.approvals import pending_approval_ids
from chat_lms_agent.cli_io import write_json
from chat_lms_agent.goal_state import goal_status
from chat_lms_agent.memory_obligations import obligations_for_reason
from chat_lms_agent.state import (
    JsonValue,
    ProfileState,
    bump_consecutive_marker,
    load_memory,
    load_tools,
    read_state_mapping,
    write_state_mapping,
)

COMPACT_RECOVERY_FILE: Final = "compact-recovery.json"
STOP_BLOCK_COUNTER_KEY: Final = "stop-block"
ESCALATION_THRESHOLD: Final = 3


def write_closeout(profile: ProfileState) -> int:
    code, payload = compute_closeout(profile)
    write_json(payload)
    return code


def compute_closeout(profile: ProfileState) -> tuple[int, dict[str, JsonValue]]:
    pending_approvals = pending_approval_ids(profile)
    import_plans = unapplied_import_plan_ids(profile)
    if pending_approvals or import_plans:
        approval_values: list[JsonValue] = []
        approval_values.extend(pending_approvals)
        plan_values: list[JsonValue] = []
        plan_values.extend(import_plans)
        return 5, {
            "status": "BLOCKED",
            "decision": "block",
            "pending_approvals": approval_values,
            "unapplied_import_plans": plan_values,
            "reason": _render_reason(pending_approvals, import_plans, []),
        }
    missing = _missing_memory(profile)
    if missing:
        missing_memory: list[JsonValue] = []
        missing_memory.extend(missing)
        return 5, {
            "status": "BLOCKED",
            "decision": "block",
            "missing_memory": missing_memory,
            "reason": _render_reason([], [], missing),
        }
    return 0, {"status": "PASS", "missing_memory": []}


def write_stop_closeout(
    profile: ProfileState,
    session_id: str | None,
    *,
    stop_hook_active: bool,
) -> int:
    if stop_hook_active:
        write_json({"status": "PASS", "skipped": "stop_hook_active"})
        return 0
    code, payload = compute_closeout(profile)
    if code == 0:
        write_json(payload)
        return 0
    signature = _blocker_signature(payload)
    count = bump_consecutive_marker(profile, session_id, STOP_BLOCK_COUNTER_KEY, signature)
    if count >= ESCALATION_THRESHOLD:
        write_json(
            {
                "status": "PASS",
                "escalated": True,
                "warning": "ESCALATED_AFTER_REPEATED_BLOCKS",
                "blocked_human_action_ko": (
                    "같은 차단 사유가 3회 연속 해결되지 않아 세션 차단을 멈춥니다. "
                    "교사가 아래 안내를 직접 처리해 주세요."
                ),
                "reason": payload["reason"],
            },
        )
        return 0
    write_json(payload)
    return 5


def record_compact_event(profile: ProfileState) -> None:
    write_state_mapping(profile, COMPACT_RECOVERY_FILE, {"pending": True})


def claim_compact_recovery(
    profile: ProfileState,
    source: str | None,
) -> dict[str, JsonValue] | None:
    marker = read_state_mapping(profile, COMPACT_RECOVERY_FILE)
    pending = marker.get("pending") is True
    if source != "compact" and not pending:
        return None
    write_state_mapping(profile, COMPACT_RECOVERY_FILE, {"pending": False})
    _, closeout = compute_closeout(profile)
    return {
        "schema_version": "compact-recovery-v1",
        "closeout_status": closeout["status"],
        "missing_memory": closeout.get("missing_memory", []),
        "pending_approvals": closeout.get("pending_approvals", []),
        "unapplied_import_plans": closeout.get("unapplied_import_plans", []),
        "goals": goal_status(profile),
    }


def _render_reason(
    pending_approvals: list[str],
    import_plans: list[str],
    missing: list[str],
) -> str:
    cli = "python -m chat_lms_agent"
    upsert_sfx = '--scope durable --text "<기록할 내용>" --profile-root <root> --json'
    approve_sfx = "--actor human:owner --profile-root <root> --json"
    apply_sfx = "--approval-id <approval-id> --profile-root <root> --json"
    lines = ["세션을 닫기 전에 아래 항목을 처리해야 합니다."]
    lines.extend(
        f"- 메모리 미기록({key}): {cli} memory upsert --key {key} {upsert_sfx}"
        for key in missing
    )
    approve_cmd = f"{cli} approval approve --approval-id"
    lines.extend(
        f"- 대기 중 승인({aid}): 교사 PowerShell 창에서 {approve_cmd} {aid} {approve_sfx}"
        for aid in pending_approvals
    )
    lines.extend(
        f"- 미적용 import plan({pid}): 승인 후 {cli} academy-db import apply {apply_sfx}"
        for pid in import_plans
    )
    return "\n".join(lines)


def _blocker_signature(payload: dict[str, JsonValue]) -> str:
    parts: list[str] = []
    for key in ("missing_memory", "pending_approvals", "unapplied_import_plans"):
        values = payload.get(key)
        if isinstance(values, list):
            parts.extend(sorted(str(value) for value in values))
    return "|".join(parts)


def _missing_memory(profile: ProfileState) -> list[str]:
    memory_keys = {entry["key"] for entry in load_memory(profile)}
    missing = _missing_legacy_tool_memory(profile, memory_keys)
    if store_path(profile).exists():
        for obligation in obligations_for_reason("academy-db-init"):
            if obligation.key not in memory_keys:
                missing.append(obligation.key)
    return sorted(missing)


def _missing_legacy_tool_memory(profile: ProfileState, memory_keys: set[str]) -> list[str]:
    tools = [tool for tool in load_tools(profile) if tool["status"] == "active"]
    return [
        f"tool:{tool['name']}"
        for tool in tools
        if f"tool:{tool['name']}" not in memory_keys
    ]
