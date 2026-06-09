from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from chat_lms_agent.agent_tools import (
    agent_tools_context,
    memory_policy_context,
    tool_registry_context,
)
from chat_lms_agent.approvals import approval_context
from chat_lms_agent.harness_context import (
    academy_db_context,
    hook_lifecycle_context,
    memory_obligations_context,
    tool_lifecycle_context,
)
from chat_lms_agent.harness_events import harness_context_v3
from chat_lms_agent.journal import audit_context, redact_runtime_text, trace_context
from chat_lms_agent.oss_references import oss_reference_context
from chat_lms_agent.side_panel import side_panel_contract_shape
from chat_lms_agent.state import (
    JsonValue,
    load_memory,
    load_tools,
    resolve_profile_state,
)


def build_codex_context(
    repo_root: Path,
    profile_root: str | None = None,
    profile: str | None = None,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "status": "PASS",
        "runtime": "Codex Desktop",
        "workspace": repo_root.name,
        "db": "not-initialized",
        "credential_health": "redacted",
        "next_actions": ["run onboarding"],
        "active_tools": [],
        "memory": [],
        "side_panel": side_panel_contract_shape(),
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
    }
    profile_state = resolve_profile_state(repo_root, profile_root, profile)
    if isinstance(profile_state, str):
        payload["status"] = "UNSAFE"
        payload["warnings"] = [profile_state]
        return payload

    tools = [tool for tool in load_tools(profile_state) if tool["status"] == "active"]
    memories = load_memory(profile_state)
    payload["academy_db"] = academy_db_context(profile_state)
    payload["context_map"] = {
        "schema_version": "context-map-v1",
        "command": "python -m chat_lms_agent context map build --profile-root <root> --json",
        "truth_source": "generated_from_canonical_sources",
    }
    payload["trace"] = trace_context(profile_state)
    payload["audit"] = audit_context(profile_state)
    payload["approvals"] = approval_context(profile_state)
    payload["active_tools"] = [
        {
            "name": tool["name"],
            "kind": tool["kind"],
            "summary": redact_runtime_text(profile_state, tool["summary"]),
            "command": (
                redact_runtime_text(profile_state, tool["command"])
                if tool["command"] is not None
                else None
            ),
        }
        for tool in tools
    ]
    payload["memory"] = [
        {
            "key": entry["key"],
            "scope": entry["scope"],
            "text": redact_runtime_text(profile_state, entry["text"]),
        }
        for entry in memories
    ]
    return payload
