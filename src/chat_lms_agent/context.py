from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

from chat_lms_agent.academy_db import store_path
from chat_lms_agent.academy_db_imports import unapplied_import_plan_ids
from chat_lms_agent.agent_tools import (
    agent_tools_context,
    memory_policy_context,
    tool_registry_context,
)
from chat_lms_agent.approvals import approval_context, pending_approval_ids
from chat_lms_agent.harness_context import (
    academy_db_context,
    hook_lifecycle_context,
    memory_obligations_context,
    tool_lifecycle_context,
)
from chat_lms_agent.harness_events import harness_context_v3
from chat_lms_agent.hosts import active_host
from chat_lms_agent.journal import audit_context, redact_runtime_text, trace_context
from chat_lms_agent.memory_levels import memory_levels_payload
from chat_lms_agent.memory_recall import recall_memory
from chat_lms_agent.model_catalog import catalog_context
from chat_lms_agent.oss_references import oss_reference_context
from chat_lms_agent.prompt_route_policy import prompt_routing_policy_context
from chat_lms_agent.route_packs import load_route_packs, route_packs_context
from chat_lms_agent.side_panel import side_panel_contract_shape
from chat_lms_agent.state import (
    JsonValue,
    ProfileState,
    load_memory,
    resolve_profile_state,
)
from chat_lms_agent.tool_store import ComposedTool, usable_tools

CONTEXT_EVENT_BYTE_CEILING: Final = 13_800
CONTEXT_SECTION_BYTE_CEILINGS: Final[dict[str, int]] = {
    "memory": 12_000,
    "oss_reference_registry": 3_500,
    "side_panel": 2_400,
    "prompt_routing": 1_400,
    "route_packs": 4_500,
}
APPLIED_REDUCTIONS: Final[tuple[dict[str, str], ...]] = (
    {
        "step": "journal_counts_removed",
        "detail": "trace/audit live record counts replaced by stable list commands",
    },
    {
        "step": "event_tiering",
        "detail": "UserPromptSubmit emits route+deltas only; PostToolUse emits on obligation only",
    },
    {
        "step": "memory_section_budget",
        "detail": "memory section truncates at its byte ceiling with an explicit marker",
    },
    {
        "step": "oss_registry_slimmed",
        "detail": "hydration carries registry ids and adoption status only; the doc is canonical",
    },
    {
        "step": "route_command_index_compacted",
        "detail": "SessionStart carries compact route commands with route-pack recovery hints",
    },
)
_MEMORY_TRUNCATION_HINT: Final = (
    "python -m chat_lms_agent memory list --profile-root <root> --json"
)


def build_host_context(
    repo_root: Path,
    profile_root: str | None = None,
    profile: str | None = None,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "status": "PASS",
        "runtime": active_host().runtime_label,
        "workspace": "<workspace>",
        "db": "not-initialized",
        "credential_health": "redacted",
        "cli_entrypoint": _cli_entrypoint_context(),
        "next_actions": ["run onboarding"],
        "active_tools": [],
        "memory": [],
        "side_panel": side_panel_contract_shape(),
        "prompt_routing": prompt_routing_policy_context(),
        "harness": harness_context_v3(),
        "trace": trace_context(None),
        "audit": audit_context(None),
        "approvals": approval_context(None),
        "agent_tools": agent_tools_context(),
        "tool_registry": tool_registry_context(),
        "memory_policy": memory_policy_context(),
        "hook_lifecycle": hook_lifecycle_context(repo_root),
        "memory_obligations": memory_obligations_context(),
        "tool_lifecycle": tool_lifecycle_context(),
        "academy_db": academy_db_context(None),
        "oss_reference_registry": oss_reference_context(),
        "model_catalog": catalog_context(repo_root),
        "route_packs": route_packs_context(load_route_packs(repo_root)[0]),
    }
    profile_state = resolve_profile_state(repo_root, profile_root, profile)
    if isinstance(profile_state, str):
        payload["status"] = "UNSAFE"
        payload["warnings"] = [profile_state]
        return payload

    tools = [tool for tool in usable_tools(profile_state) if tool["source"] != "static"]
    memories = load_memory(profile_state)
    payload["db"] = _db_status(profile_state)
    payload["academy_db"] = academy_db_context(profile_state)
    payload["context_map"] = {
        "schema_version": "context-map-v1",
        "command": "python -m chat_lms_agent context map build --profile-root <root> --json",
        "truth_source": "generated_from_canonical_sources",
    }
    payload["trace"] = trace_context(profile_state)
    payload["audit"] = audit_context(profile_state)
    payload["approvals"] = approval_context(profile_state)
    payload["model_catalog"] = catalog_context(profile_state.repo_root, profile_state)
    payload["route_packs"] = route_packs_context(
        load_route_packs(profile_state.repo_root, profile_state)[0],
    )
    payload["active_tools"] = [
        {
            "name": tool["id"],
            "kind": tool["kind"],
            "summary": redact_runtime_text(profile_state, tool["summary"]),
            "command": _first_command(profile_state, tool),
            "source": tool["source"],
        }
        for tool in tools
    ]
    hydratable: list[JsonValue] = [
        {
            "key": entry["key"],
            "scope": entry["scope"],
            "text": redact_runtime_text(profile_state, entry["text"]),
        }
        for entry in memories
        if entry.get("level") not in _non_hydrated_levels()
    ]
    payload["memory"] = _budget_memory_section(hydratable)
    return payload


def build_prompt_delta_context(
    profile_state: ProfileState,
    prompt: str | None,
) -> dict[str, JsonValue]:
    """Per-prompt delta payload: actionable state only, no static sections."""
    deltas: dict[str, JsonValue] = {
        "pending_approvals": list(pending_approval_ids(profile_state)),
        "unapplied_import_plans": list(unapplied_import_plan_ids(profile_state)),
    }
    if prompt is not None:
        recalled = recall_memory(load_memory(profile_state), prompt)
        deltas["memory_recall"] = [
            {
                "key": entry["key"],
                "scope": entry["scope"],
                "text": redact_runtime_text(profile_state, entry["text"]),
            }
            for entry in recalled
        ]
    return {
        "status": "PASS",
        "schema_version": "prompt-delta-v1",
        "deltas": deltas,
    }


def _non_hydrated_levels() -> frozenset[str]:
    levels = memory_levels_payload().get("levels")
    if not isinstance(levels, list):
        return frozenset()
    excluded: set[str] = set()
    for level in levels:
        if (
            isinstance(level, dict)
            and level.get("hydrated_by_default") is False
            and isinstance(level.get("id"), str)
        ):
            excluded.add(str(level["id"]))
    return frozenset(excluded)


def _budget_memory_section(entries: list[JsonValue]) -> list[JsonValue]:
    ceiling = CONTEXT_SECTION_BYTE_CEILINGS["memory"]
    if _blob_size(entries) <= ceiling:
        return entries
    kept: list[JsonValue] = []
    for entry in entries:
        marker = _truncation_marker(len(entries) - len(kept) - 1)
        if _blob_size([*kept, entry, marker]) > ceiling:
            break
        kept.append(entry)
    return [*kept, _truncation_marker(len(entries) - len(kept))]


def _truncation_marker(omitted: int) -> dict[str, JsonValue]:
    return {"truncated": True, "omitted": omitted, "hint": _MEMORY_TRUNCATION_HINT}


def _blob_size(value: JsonValue) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _first_command(profile_state: ProfileState, tool: ComposedTool) -> str | None:
    commands = tool["command_contract"].get("commands")
    if isinstance(commands, list) and commands and isinstance(commands[0], str):
        return redact_runtime_text(profile_state, commands[0])
    return None


def _db_status(profile_state: ProfileState) -> str:
    sqlite_path = profile_state.root / "data" / "chat_lms.db"
    if store_path(profile_state).exists() or sqlite_path.exists():
        return "initialized"
    return "not-initialized"


def _cli_entrypoint_context() -> dict[str, JsonValue]:
    workspace = active_host().workspace_dirname
    cli_script = f"<profile-root>/{workspace}/scripts/chat-lms-cli.ps1"
    return {
        "preferred_private_entrypoint": cli_script,
        "windows_command_template": (
            f"powershell -NoProfile -ExecutionPolicy Bypass -File {cli_script} <args>"
        ),
        "avoid": ["bare python -m chat_lms_agent in private workspace"],
    }
