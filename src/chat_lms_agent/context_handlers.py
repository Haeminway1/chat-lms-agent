from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent.cli_io import (
    flag,
    profile_options,
    profile_state_or_error,
    required_option,
    write_json,
)
from chat_lms_agent.context import build_host_context
from chat_lms_agent.context_v4 import (
    budget_payload,
    build_context_map,
    get_offload,
    put_offload,
    show_context_map,
)

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

TOP_LEVEL_ARGS: int = 2
NESTED_ARGS: int = 3


def handle_context(args: list[str], repo_root: Path) -> int:
    if len(args) >= TOP_LEVEL_ARGS and args[1] == "hydrate":
        profile_root, profile = profile_options(args)
        write_json(build_host_context(repo_root, profile_root, profile))
        return 0
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    route = tuple(args[1:3]) if len(args) >= NESTED_ARGS else ()
    code, payload = _profile_context_payload(args, route, profile)
    write_json(payload)
    return code


def _profile_context_payload(
    args: list[str],
    route: tuple[str, ...],
    profile: ProfileState,
) -> tuple[int, dict[str, JsonValue]]:
    match route:
        case ("map", "build"):
            return 0, build_context_map(profile)
        case ("map", "show"):
            return show_context_map(profile)
        case ("offload", "put"):
            return put_offload(
                profile,
                required_option(args, "--kind"),
                Path(required_option(args, "--from")),
            )
        case ("offload", "get"):
            return get_offload(
                profile,
                required_option(args, "--ref"),
                reveal=flag(args, "--reveal"),
            )
        case ("budget", "show"):
            return 0, budget_payload(profile)
        case _:
            return 2, {"status": "ERROR", "error_code": "UNKNOWN_CONTEXT_COMMAND"}
