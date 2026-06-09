from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, TypedDict, cast

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

REGISTRY_VERSION: Final = "1"
REGISTRY_MEMORY_OBLIGATION: Final = (
    "Any reusable agent tool or registry change must update the durable tool memory "
    "contract before closeout."
)
TOOL_MEMORY_KEY_PATTERN: Final = "tool:<id>"
REGISTRY_MANAGED_PATHS: Final = (
    "src/chat_lms_agent/agent_tools.py",
    "src/chat_lms_agent/agent_tool_handlers.py",
    "docs/agent-tool-registry.md",
)
SIDE_PANEL_PAYLOAD_VALIDATE_PREFIX: Final = (
    "python -m chat_lms_agent side-panel payload validate --from"
)
SIDE_PANEL_PAYLOAD_VALIDATE_COMMAND: Final = (
    f"{SIDE_PANEL_PAYLOAD_VALIDATE_PREFIX} <payload.json> --json"
)


class AgentTool(TypedDict):
    id: str
    label: str
    kind: str
    status: str
    summary: str
    command_contract: dict[str, JsonValue]
    memory_obligation: str
    source: str


@dataclass(frozen=True, slots=True)
class ProposalValidation:
    proposal_id: str | None
    errors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ToolSpec:
    tool_id: str
    label: str
    kind: str
    status: str
    summary: str
    commands: tuple[str, ...]
    memory_obligation: str


def default_agent_tools() -> tuple[AgentTool, ...]:
    return (
        _tool(
            _ToolSpec(
                tool_id="side-panel",
                label="Side Panel",
                kind="ui_building_block",
                status="active",
                summary="Create Codex Desktop auxiliary panel payloads from approved blocks.",
                commands=(
                    "python -m chat_lms_agent side-panel spec --json",
                    "python -m chat_lms_agent side-panel block list --json",
                    SIDE_PANEL_PAYLOAD_VALIDATE_COMMAND,
                ),
                memory_obligation="Record tool:side-panel when panel blocks or rules change.",
            ),
        ),
        _tool(
            _ToolSpec(
                tool_id="academy-db",
                label="Academy DB",
                kind="database_workflow",
                status="planned",
                summary=(
                    "Reusable contracts for teacher-owned academy database setup and operations."
                ),
                commands=(
                    "python -m chat_lms_agent agent-tools validate --from <db-tool.json> --json",
                    "python -m chat_lms_agent context hydrate --for-codex --json",
                ),
                memory_obligation="Record tool:academy-db before relying on a new DB workflow.",
            ),
        ),
    )


def agent_tools_payload() -> dict[str, JsonValue]:
    tools: list[JsonValue] = [_tool_json(tool) for tool in default_agent_tools()]
    return {
        "status": "PASS",
        "registry_version": REGISTRY_VERSION,
        "source": "public_repo_default_registry",
        "memory_obligation": REGISTRY_MEMORY_OBLIGATION,
        "tools": tools,
    }


def agent_tools_context() -> list[JsonValue]:
    return [
        {
            "id": tool["id"],
            "status": tool["status"],
            "summary": tool["summary"],
            "memory_obligation": tool["memory_obligation"],
        }
        for tool in default_agent_tools()
    ]


def tool_registry_context() -> dict[str, JsonValue]:
    return {
        "source": "public_repo_default_registry",
        "registry_version": REGISTRY_VERSION,
        "command": "python -m chat_lms_agent agent-tools list --json",
        "proposal_validation": (
            "python -m chat_lms_agent agent-tools validate --from <proposal.json> --json"
        ),
        "memory_obligation": REGISTRY_MEMORY_OBLIGATION,
        "tool_count": len(default_agent_tools()),
    }


def memory_policy_context() -> dict[str, JsonValue]:
    return {
        "registry_memory_obligation": REGISTRY_MEMORY_OBLIGATION,
        "tool_memory_key_pattern": TOOL_MEMORY_KEY_PATTERN,
        "registry_change_rule": (
            "Reusable tool changes must include a command contract and a memory obligation."
        ),
        "public_private_boundary": (
            "The public repo stores tool contracts only; runtime memory remains in profile "
            ".chat-lms-state."
        ),
    }


def validate_agent_tool_proposal(path: Path) -> ProposalValidation:
    payload = _load_json_object(path)
    if payload is None:
        return ProposalValidation(proposal_id=None, errors=("INVALID_JSON",))

    errors: list[str] = []
    raw_id = payload.get("id")
    proposal_id = raw_id if isinstance(raw_id, str) else None
    if proposal_id is None:
        errors.append("MISSING_ID")
    if not _has_memory_obligation(payload.get("memory_obligation")):
        errors.append("MISSING_MEMORY_OBLIGATION")
    if not _has_command_contract(payload.get("command_contract")):
        errors.append("MISSING_COMMAND_CONTRACT")
    if not _non_empty_string(payload.get("summary")):
        errors.append("MISSING_SUMMARY")
    return ProposalValidation(proposal_id=proposal_id, errors=tuple(errors))


def validation_payload(result: ProposalValidation) -> dict[str, JsonValue]:
    if not result.errors:
        return {
            "status": "PASS",
            "proposal_id": result.proposal_id,
            "memory_obligation": REGISTRY_MEMORY_OBLIGATION,
        }
    return {
        "status": "ERROR",
        "error_code": "INVALID_TOOL_PROPOSAL",
        "proposal_id": result.proposal_id,
        "errors": list(result.errors),
    }


def parse_changed_files(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    normalized = value.replace(";", ",").replace("\n", ",")
    return tuple(item.strip().replace("\\", "/") for item in normalized.split(",") if item.strip())


def touches_agent_tool_registry(changed_files: tuple[str, ...]) -> bool:
    managed = set(REGISTRY_MANAGED_PATHS)
    return any(file_path in managed for file_path in changed_files)


def memory_update_required_payload(changed_files: tuple[str, ...]) -> dict[str, JsonValue]:
    return {
        "status": "BLOCKED",
        "error_code": "MEMORY_UPDATE_REQUIRED",
        "message": "agent tool registry changes require a durable memory update",
        "memory_obligation": REGISTRY_MEMORY_OBLIGATION,
        "changed_files": list(changed_files),
    }


def _tool(spec: _ToolSpec) -> AgentTool:
    command_values: list[JsonValue] = list(spec.commands)
    command_contract: dict[str, JsonValue] = {
        "commands": command_values,
        "json_required": True,
        "public_safe": True,
    }
    return {
        "id": spec.tool_id,
        "label": spec.label,
        "kind": spec.kind,
        "status": spec.status,
        "summary": spec.summary,
        "command_contract": command_contract,
        "memory_obligation": spec.memory_obligation,
        "source": "public_repo_default_registry",
    }


def _tool_json(tool: AgentTool) -> dict[str, JsonValue]:
    return {
        "id": tool["id"],
        "label": tool["label"],
        "kind": tool["kind"],
        "status": tool["status"],
        "summary": tool["summary"],
        "command_contract": tool["command_contract"],
        "memory_obligation": tool["memory_obligation"],
        "source": tool["source"],
    }


def _load_json_object(path: Path) -> dict[str, JsonValue] | None:
    try:
        raw = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return None
    if isinstance(raw, dict):
        return raw
    return None


def _has_memory_obligation(value: JsonValue | None) -> bool:
    if _non_empty_string(value):
        return True
    if not isinstance(value, dict):
        return False
    key = value.get("key")
    scope = value.get("scope")
    text = value.get("text")
    return _non_empty_string(key) and _non_empty_string(scope) and _non_empty_string(text)


def _has_command_contract(value: JsonValue | None) -> bool:
    if not isinstance(value, dict):
        return False
    command = value.get("command")
    commands = value.get("commands")
    if _non_empty_string(command):
        return True
    return isinstance(commands, list) and any(_non_empty_string(item) for item in commands)


def _non_empty_string(value: JsonValue | None) -> bool:
    return isinstance(value, str) and bool(value.strip())
