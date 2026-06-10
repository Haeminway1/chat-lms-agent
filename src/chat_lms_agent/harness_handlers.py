from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

from chat_lms_agent.cli_io import option, profile_state_or_error, required_option, write_json
from chat_lms_agent.harness_events import normalize_event_file
from chat_lms_agent.model_catalog import list_catalog, resolve_role, validate_catalog

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

NORMALIZE_ROUTE_LENGTH: Final = 3
MODEL_ROUTE_LENGTH: Final = 2


def handle_harness(args: list[str], repo_root: Path) -> int:
    if len(args) >= NORMALIZE_ROUTE_LENGTH and args[1:3] == ["event", "normalize"]:
        payload = normalize_event_file(Path(required_option(args, "--from")))
        write_json(payload)
        return 0 if payload["status"] == "PASS" else 2
    if len(args) >= MODEL_ROUTE_LENGTH and args[1] == "model":
        return _handle_model(args, repo_root)
    write_json({"status": "ERROR", "error_code": "UNKNOWN_HARNESS_COMMAND"})
    return 2


def _handle_model(args: list[str], repo_root: Path) -> int:
    profile = _optional_profile(args, repo_root)
    if isinstance(profile, str):
        return 4
    verb = args[2] if len(args) > MODEL_ROUTE_LENGTH else ""
    payload: dict[str, JsonValue]
    if verb == "resolve":
        payload = resolve_role(repo_root, required_option(args, "--role"), profile)
    elif verb == "list":
        payload = list_catalog(repo_root, profile)
    elif verb == "validate":
        payload = validate_catalog(repo_root, profile)
    else:
        payload = {"status": "ERROR", "error_code": "UNKNOWN_MODEL_COMMAND"}
    write_json(payload)
    return 0 if payload["status"] == "PASS" else 2


def _optional_profile(args: list[str], repo_root: Path) -> ProfileState | str | None:
    if option(args, "--profile-root") is None and option(args, "--profile") is None:
        return None
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return "unsafe"
    return profile
