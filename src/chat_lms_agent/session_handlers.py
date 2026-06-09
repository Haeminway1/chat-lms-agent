from __future__ import annotations

from typing import TYPE_CHECKING

from chat_lms_agent.cli_io import profile_state_or_error, subcommand, write_json
from chat_lms_agent.journal import audit_refs, trace_refs
from chat_lms_agent.session_closeout import write_closeout

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState


def handle_session(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    command = subcommand(args)
    if command == "closeout":
        return write_closeout(profile)
    if command == "summarize":
        write_json(session_summary(profile))
        return 0
    write_json({"status": "ERROR", "error_code": "UNKNOWN_SESSION_COMMAND"})
    return 2


def session_summary(profile: ProfileState) -> dict[str, JsonValue]:
    trace_values: list[JsonValue] = []
    trace_values.extend(trace_refs(profile))
    audit_values: list[JsonValue] = []
    audit_values.extend(audit_refs(profile))
    return {
        "status": "PASS",
        "schema_version": "session-summary-v1",
        "profile_root": "<profile-root>",
        "trace_refs": trace_values,
        "audit_refs": audit_values,
    }
