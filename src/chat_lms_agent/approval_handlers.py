from __future__ import annotations

from typing import TYPE_CHECKING

from chat_lms_agent.approvals import (
    approve_request,
    deny_request,
    list_approvals,
    show_approval,
)
from chat_lms_agent.cli_io import (
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)

if TYPE_CHECKING:
    from pathlib import Path


def handle_approval(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    command = subcommand(args)
    if command == "list":
        write_json(list_approvals(profile))
        return 0
    if command == "show":
        code, payload = show_approval(profile, required_option(args, "--approval-id"))
        write_json(payload)
        return code
    if command == "approve":
        code, payload = approve_request(
            profile,
            required_option(args, "--approval-id"),
            required_option(args, "--actor"),
        )
        write_json(payload)
        return code
    if command == "deny":
        code, payload = deny_request(
            profile,
            required_option(args, "--approval-id"),
            required_option(args, "--actor"),
        )
        write_json(payload)
        return code
    write_json({"status": "ERROR", "error_code": "UNKNOWN_APPROVAL_COMMAND"})
    return 2
