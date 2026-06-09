from __future__ import annotations

from pathlib import Path

from chat_lms_agent.cli_io import profile_state_or_error, required_option, write_json
from chat_lms_agent.goal_state import add_goal_evidence, goal_status, verify_goal

TOP_LEVEL_ARGS: int = 2
NESTED_ARGS: int = 3


def handle_goal(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    if len(args) >= TOP_LEVEL_ARGS and args[1] == "status":
        write_json(goal_status(profile))
        return 0
    if len(args) >= TOP_LEVEL_ARGS and args[1] == "verify":
        code, payload = verify_goal(profile, required_option(args, "--goal-id"))
        write_json(payload)
        return code
    if len(args) >= NESTED_ARGS and args[1:3] == ["evidence", "add"]:
        code, payload = add_goal_evidence(
            profile,
            required_option(args, "--goal-id"),
            Path(required_option(args, "--from")),
        )
        write_json(payload)
        return code
    write_json({"status": "ERROR", "error_code": "UNKNOWN_GOAL_COMMAND"})
    return 2
