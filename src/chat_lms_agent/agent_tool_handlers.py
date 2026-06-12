from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent.agent_tool_lifecycle import (
    explain_tool,
    lifecycle_doctor,
    scaffold_tool,
    set_lifecycle_state,
)
from chat_lms_agent.agent_tool_reuse import reuse_check_payload
from chat_lms_agent.agent_tools import (
    agent_tools_payload,
    validate_agent_tool_proposal,
    validation_payload,
)
from chat_lms_agent.cli_io import (
    option,
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)
from chat_lms_agent.prompt_routes import WORDBOOK_ROUTE_ID, prompt_check_payload
from chat_lms_agent.route_packs import load_route_packs
from chat_lms_agent.usage_telemetry import record_surface_use

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState


def handle_agent_tools(args: list[str], repo_root: Path | None = None) -> int:
    command = subcommand(args)
    if command in {"list", "validate", "reuse-check", "prompt-check"}:
        return _handle_public_command(args, command, repo_root)
    if repo_root is None:
        write_json({"status": "ERROR", "error_code": "MISSING_REPO_ROOT"})
        return 2
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    return _handle_profile_command(args, command, profile)


def _handle_public_command(args: list[str], command: str, repo_root: Path | None) -> int:
    if command == "list":
        write_json(agent_tools_payload())
        return 0
    if command in {"reuse-check", "prompt-check"}:
        return _handle_check_command(args, command, repo_root)
    result = validate_agent_tool_proposal(Path(required_option(args, "--from")))
    write_json(validation_payload(result))
    if not result.errors:
        return 0
    return 2


def _handle_check_command(args: list[str], command: str, repo_root: Path | None) -> int:
    profile = _optional_profile(args, repo_root)
    if isinstance(profile, str):
        return 4
    if command == "reuse-check":
        write_json(reuse_check_payload(required_option(args, "--intent"), repo_root, profile))
        return 0
    payload = prompt_check_payload(required_option(args, "--prompt"), repo_root, profile)
    write_json(payload)
    return 0 if payload["status"] == "PASS" else 2


def _handle_profile_command(args: list[str], command: str, profile: ProfileState) -> int:
    payload: dict[str, JsonValue]
    match command:
        case "route":
            return _handle_route_command(args, profile)
        case "scaffold":
            payload = scaffold_tool(profile, Path(required_option(args, "--from")))
        case "register":
            payload = set_lifecycle_state(profile, required_option(args, "--id"), "registered")
        case "promote":
            payload = set_lifecycle_state(
                profile,
                required_option(args, "--id"),
                "active",
                evidence=option(args, "--evidence"),
            )
        case "deprecate":
            payload = set_lifecycle_state(profile, required_option(args, "--id"), "deprecated")
        case "explain":
            payload = explain_tool(profile, required_option(args, "--id"))
        case "doctor":
            payload = lifecycle_doctor(profile)
        case _:
            payload = {"status": "ERROR", "error_code": "UNKNOWN_AGENT_TOOLS_COMMAND"}
    write_json(payload)
    return 0 if payload["status"] == "PASS" else 2


def _handle_route_command(args: list[str], profile: ProfileState) -> int:
    route_command = _subcommand_at(args, 2)
    if route_command != "record":
        write_json({"status": "ERROR", "error_code": "UNKNOWN_AGENT_TOOLS_ROUTE_COMMAND"})
        return 2
    route_id = required_option(args, "--route-id")
    if route_id not in _known_route_ids(profile):
        write_json({"status": "ERROR", "error_code": "UNKNOWN_ROUTE_ID", "route_id": route_id})
        return 2
    count = record_surface_use(profile, f"route-catalog:{route_id}")
    write_json(
        {
            "status": "PASS",
            "route_id": route_id,
            "telemetry_key": f"route-catalog:{route_id}",
            "count": count,
        },
    )
    return 0


def _known_route_ids(profile: ProfileState) -> frozenset[str]:
    packs, _warnings = load_route_packs(profile.repo_root, profile)
    return frozenset((WORDBOOK_ROUTE_ID, *(pack.pack_id for pack in packs)))


def _optional_profile(args: list[str], repo_root: Path | None) -> ProfileState | str | None:
    if option(args, "--profile-root") is None and option(args, "--profile") is None:
        return None
    if repo_root is None:
        write_json({"status": "ERROR", "error_code": "MISSING_REPO_ROOT"})
        return "unsafe"
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return "unsafe"
    return profile


def _subcommand_at(args: list[str], index: int) -> str:
    if len(args) <= index:
        return ""
    return args[index]
