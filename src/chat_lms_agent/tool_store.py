"""Single composed read path over the three tool stores.

The static public registry, the legacy per-profile ``tools.json``, and the
agent-tool lifecycle store previously had independent readers, so a
teacher-promoted lifecycle tool was invisible to the reuse gate and to
context hydration (gap-analysis P0-7). Every reader now composes the three
sources through this module, with each entry tagged by its source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, TypedDict

from chat_lms_agent.agent_tool_lifecycle import load_lifecycle_records
from chat_lms_agent.agent_tools import default_agent_tools
from chat_lms_agent.state import load_tools, redact_text

if TYPE_CHECKING:
    from chat_lms_agent.agent_tool_lifecycle import AgentToolLifecycleRecord
    from chat_lms_agent.agent_tools import AgentTool
    from chat_lms_agent.state import JsonValue, ProfileState, ToolPayload

type ToolSource = Literal["static", "legacy", "lifecycle"]


class ComposedTool(TypedDict):
    id: str
    label: str
    kind: str
    status: str
    source: ToolSource
    summary: str
    command_contract: dict[str, JsonValue]
    memory_obligation: JsonValue


def composed_tools(profile: ProfileState | None = None) -> list[ComposedTool]:
    entries: list[ComposedTool] = [_from_static(tool) for tool in default_agent_tools()]
    if profile is None:
        return entries
    entries.extend(_from_legacy(tool) for tool in load_tools(profile))
    entries.extend(
        _from_lifecycle(record) for record in load_lifecycle_records(profile).values()
    )
    return entries


def usable_tools(profile: ProfileState | None = None) -> list[ComposedTool]:
    """Tools the agent may rely on right now: the static registry plus active entries."""
    return [
        tool
        for tool in composed_tools(profile)
        if tool["source"] == "static" or tool["status"] == "active"
    ]


def _from_static(tool: AgentTool) -> ComposedTool:
    return {
        "id": tool["id"],
        "label": tool["label"],
        "kind": tool["kind"],
        "status": tool["status"],
        "source": "static",
        "summary": tool["summary"],
        "command_contract": tool["command_contract"],
        "memory_obligation": tool["memory_obligation"],
    }


def _from_legacy(tool: ToolPayload) -> ComposedTool:
    commands: list[JsonValue] = []
    if tool["command"] is not None:
        commands.append(tool["command"])
    return {
        "id": tool["name"],
        "label": tool["name"],
        "kind": tool["kind"],
        "status": tool["status"],
        "source": "legacy",
        "summary": redact_text(tool["summary"]),
        "command_contract": {"commands": commands},
        "memory_obligation": f"tool:{tool['name']}",
    }


def _from_lifecycle(record: AgentToolLifecycleRecord) -> ComposedTool:
    return {
        "id": record["id"],
        "label": record["label"],
        "kind": "lifecycle_tool",
        "status": record["lifecycle_state"],
        "source": "lifecycle",
        "summary": redact_text(record["summary"]),
        "command_contract": record["command_contract"],
        "memory_obligation": record["memory_obligation"],
    }
