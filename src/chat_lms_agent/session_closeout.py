from __future__ import annotations

from chat_lms_agent.academy_db import store_path
from chat_lms_agent.academy_db_imports import unapplied_import_plan_ids
from chat_lms_agent.approvals import pending_approval_ids
from chat_lms_agent.cli_io import write_json
from chat_lms_agent.memory_obligations import obligations_for_reason
from chat_lms_agent.state import JsonValue, ProfileState, load_memory, load_tools


def write_closeout(profile: ProfileState) -> int:
    pending_approvals = pending_approval_ids(profile)
    import_plans = unapplied_import_plan_ids(profile)
    if pending_approvals or import_plans:
        approval_values: list[JsonValue] = []
        approval_values.extend(pending_approvals)
        plan_values: list[JsonValue] = []
        plan_values.extend(import_plans)
        write_json(
            {
                "status": "BLOCKED",
                "pending_approvals": approval_values,
                "unapplied_import_plans": plan_values,
            },
        )
        return 5
    missing = _missing_memory(profile)
    if missing:
        missing_memory: list[JsonValue] = []
        missing_memory.extend(missing)
        write_json({"status": "BLOCKED", "missing_memory": missing_memory})
        return 5
    write_json({"status": "PASS", "missing_memory": []})
    return 0


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
