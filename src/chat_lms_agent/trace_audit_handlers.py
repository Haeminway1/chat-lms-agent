from __future__ import annotations

from typing import TYPE_CHECKING

from chat_lms_agent.cli_io import profile_state_or_error, required_option, subcommand, write_json
from chat_lms_agent.journal import list_audit_records, list_trace_records, show_trace_record

if TYPE_CHECKING:
    from pathlib import Path


def handle_trace(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    if subcommand(args) == "list":
        write_json(list_trace_records(profile))
        return 0
    if subcommand(args) == "show":
        code, payload = show_trace_record(profile, required_option(args, "--id"))
        write_json(payload)
        return code
    write_json({"status": "ERROR", "error_code": "UNKNOWN_TRACE_COMMAND"})
    return 2


def handle_audit(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    if subcommand(args) == "list":
        write_json(list_audit_records(profile))
        return 0
    write_json({"status": "ERROR", "error_code": "UNKNOWN_AUDIT_COMMAND"})
    return 2
