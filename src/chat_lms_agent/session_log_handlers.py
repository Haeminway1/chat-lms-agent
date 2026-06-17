from __future__ import annotations

from typing import TYPE_CHECKING

from chat_lms_agent.cli_io import flag, option, profile_state_or_error, write_json
from chat_lms_agent.session_ledger import (
    SESSION_LEDGER_SCHEMA_VERSION,
    export_session,
    ingest_rollouts,
    is_enabled,
    list_sessions,
    set_enabled,
    show_session,
)

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState


def handle_session_log(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    verb = args[1] if len(args) > 1 else ""
    if verb in ("show", "export"):
        return _handle_read(args, profile, verb)
    payload = _handle_simple(args, profile, verb)
    write_json(payload)
    return 0 if payload.get("status") == "PASS" else 2


def _handle_simple(
    args: list[str],
    profile: ProfileState,
    verb: str,
) -> dict[str, JsonValue]:
    if verb == "ingest":
        return ingest_rollouts(profile, transcript_home=option(args, "--transcript-home"))
    if verb == "list":
        return list_sessions(profile)
    if verb == "status":
        return {
            "status": "PASS",
            "schema_version": SESSION_LEDGER_SCHEMA_VERSION,
            "enabled": is_enabled(profile),
        }
    if verb == "enable":
        return set_enabled(profile, enabled=True)
    if verb == "disable":
        return set_enabled(profile, enabled=False)
    return {"status": "ERROR", "error_code": "UNKNOWN_SESSION_LOG_COMMAND"}


def _handle_read(args: list[str], profile: ProfileState, verb: str) -> int:
    session_id = option(args, "--session-id")
    if session_id is None:
        write_json({"status": "ERROR", "error_code": "MISSING_SESSION_ID"})
        return 2
    if verb == "show":
        code, payload = show_session(profile, session_id)
    else:
        code, payload = export_session(profile, session_id, reveal=flag(args, "--reveal"))
    write_json(payload)
    return code
