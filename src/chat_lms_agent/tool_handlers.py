from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

from chat_lms_agent.state import (
    JsonValue,
    ProfileState,
    ToolPayload,
    ToolStatus,
    load_tools,
    redact_text,
    resolve_profile_state,
    save_tools,
)

SUBCOMMAND_LENGTH: Final = 2


def handle_tool(args: list[str], repo_root: Path) -> int:
    profile = _resolve_or_write_error(args, repo_root)
    if profile is None:
        return 4
    tools = load_tools(profile)
    command = _subcommand(args)
    if command == "list":
        _write_json({"status": "PASS", "tools": [_tool_json(tool) for tool in tools]})
        return 0
    if command == "draft":
        return _tool_draft(profile, args, tools)
    if command in {"activate", "deprecate"}:
        return _tool_status(profile, _required_option(args, "--name"), command, tools)
    if command == "show":
        return _tool_show(_required_option(args, "--name"), tools)
    return _json_contract_error("INVALID_TOOL_COMMAND", "unknown tool command")


def _tool_draft(profile: ProfileState, args: list[str], tools: list[ToolPayload]) -> int:
    tool: ToolPayload = {
        "name": _required_option(args, "--name"),
        "kind": _required_option(args, "--kind"),
        "summary": redact_text(_required_option(args, "--summary")),
        "command": _redacted_option(args, "--command"),
        "template": _redacted_option(args, "--template"),
        "status": "draft",
    }
    next_tools = [item for item in tools if item["name"] != tool["name"]]
    next_tools.append(tool)
    save_tools(profile, sorted(next_tools, key=lambda item: item["name"]))
    _write_json({"status": "PASS", "tool": _tool_json(tool)})
    return 0


def _tool_status(
    profile: ProfileState,
    name: str,
    status_command: str,
    tools: list[ToolPayload],
) -> int:
    status: ToolStatus = "active" if status_command == "activate" else "deprecated"
    next_tools: list[ToolPayload] = []
    found = False
    for tool in tools:
        if tool["name"] == name:
            found = True
            next_tools.append({**tool, "status": status})
        else:
            next_tools.append(tool)
    if not found:
        return _json_contract_error("TOOL_NOT_FOUND", f"tool not found: {name}")
    save_tools(profile, sorted(next_tools, key=lambda item: item["name"]))
    _write_json({"status": "PASS", "tool": name, "tool_status": status})
    return 0


def _tool_show(name: str, tools: list[ToolPayload]) -> int:
    for tool in tools:
        if tool["name"] == name:
            _write_json({"status": "PASS", "tool": _tool_json(tool)})
            return 0
    return _json_contract_error("TOOL_NOT_FOUND", f"tool not found: {name}")


def _resolve_or_write_error(args: list[str], repo_root: Path) -> ProfileState | None:
    profile_state = resolve_profile_state(
        repo_root,
        _option(args, "--profile-root"),
        _option(args, "--profile"),
    )
    if isinstance(profile_state, str):
        _write_json(
            {
                "status": "UNSAFE",
                "error_code": profile_state,
                "message": "runtime profile state cannot use the public repository root",
            },
        )
        return None
    return profile_state


def _subcommand(args: list[str]) -> str:
    if len(args) < SUBCOMMAND_LENGTH:
        return ""
    return args[1]


def _required_option(args: list[str], flag: str) -> str:
    value = _option(args, flag)
    if value is None:
        return ""
    return value


def _redacted_option(args: list[str], flag: str) -> str | None:
    value = _option(args, flag)
    if value is None:
        return None
    return redact_text(value)


def _option(args: list[str], flag: str) -> str | None:
    for index, arg in enumerate(args[:-1]):
        if arg == flag:
            return args[index + 1]
    return None


def _json_contract_error(error_code: str, message: str) -> int:
    _write_json({"status": "ERROR", "error_code": error_code, "message": message})
    return 2


def _tool_json(tool: ToolPayload) -> dict[str, JsonValue]:
    return {
        "name": tool["name"],
        "kind": tool["kind"],
        "summary": tool["summary"],
        "command": tool["command"],
        "template": tool["template"],
        "status": tool["status"],
    }


def _write_json(payload: JsonValue) -> None:
    _ = sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
