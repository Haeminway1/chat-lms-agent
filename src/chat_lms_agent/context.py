from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from chat_lms_agent.state import (
    JsonValue,
    load_memory,
    load_tools,
    redact_text,
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
    }
    profile_state = resolve_profile_state(repo_root, profile_root, profile)
    if isinstance(profile_state, str):
        payload["status"] = "UNSAFE"
        payload["warnings"] = [profile_state]
        return payload

    tools = [tool for tool in load_tools(profile_state) if tool["status"] == "active"]
    memories = load_memory(profile_state)
    payload["active_tools"] = [
        {
            "name": tool["name"],
            "kind": tool["kind"],
            "summary": redact_text(tool["summary"]),
            "command": redact_text(tool["command"]) if tool["command"] is not None else None,
        }
        for tool in tools
    ]
    payload["memory"] = [
        {
            "key": entry["key"],
            "scope": entry["scope"],
            "text": redact_text(entry["text"]),
        }
        for entry in memories
    ]
    return payload
