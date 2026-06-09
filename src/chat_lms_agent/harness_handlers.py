from __future__ import annotations

from pathlib import Path
from typing import Final

from chat_lms_agent.cli_io import required_option, write_json
from chat_lms_agent.harness_events import normalize_event_file

NORMALIZE_ROUTE_LENGTH: Final = 3


def handle_harness(args: list[str]) -> int:
    if len(args) >= NORMALIZE_ROUTE_LENGTH and args[1:3] == ["event", "normalize"]:
        payload = normalize_event_file(Path(required_option(args, "--from")))
        write_json(payload)
        return 0 if payload["status"] == "PASS" else 2
    write_json({"status": "ERROR", "error_code": "UNKNOWN_HARNESS_COMMAND"})
    return 2
