from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent.cli_io import (
    flag,
    option,
    profile_state_or_error,
    required_option,
)
from chat_lms_agent.side_panel import (
    VIEWS,
    side_panel_blocks_json,
    side_panel_spec_json,
    side_panel_view_draft,
)
from chat_lms_agent.side_panel_validation import side_panel_payload_validate
from chat_lms_agent.side_panel_wordbook import (
    DEFAULT_WORDBOOK_PORT,
    ensure_wordbook_server,
    wordbook_open_plan,
)

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


def handle_side_panel(args: list[str], repo_root: Path) -> int:
    route = _subcommand_at(args, 1)
    match route:
        case "spec":
            _write_json(side_panel_spec_json())
            return 0
        case "block":
            return _side_panel_block(args)
        case "view":
            return _side_panel_view(args)
        case "payload":
            return _side_panel_payload(args)
        case "wordbook":
            return _side_panel_wordbook(args, repo_root)
        case _:
            return _json_contract_error("INVALID_SIDE_PANEL_COMMAND", "unknown side-panel command")


def _side_panel_block(args: list[str]) -> int:
    route = _subcommand_at(args, 2)
    if route != "list":
        return _json_contract_error("INVALID_SIDE_PANEL_BLOCK_COMMAND", "unknown block command")
    _write_json(side_panel_blocks_json())
    return 0


def _side_panel_view(args: list[str]) -> int:
    route = _subcommand_at(args, 2)
    if route != "draft":
        return _json_contract_error("INVALID_SIDE_PANEL_VIEW_COMMAND", "unknown view command")
    view = _required_option(args, "--view")
    _write_json(side_panel_view_draft(view))
    return 2 if view not in VIEWS else 0


def _side_panel_payload(args: list[str]) -> int:
    route = _subcommand_at(args, 2)
    if route != "validate":
        return _json_contract_error("INVALID_SIDE_PANEL_PAYLOAD_COMMAND", "unknown payload command")
    status_code, payload = side_panel_payload_validate(Path(_required_option(args, "--from")))
    _write_json(payload)
    return status_code


def _side_panel_wordbook(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    route = _subcommand_at(args, 2)
    port = _port_option(args)
    match route:
        case "open-plan":
            code, payload = wordbook_open_plan(
                profile,
                required_option(args, "--student"),
                option(args, "--date"),
                port,
            )
        case "ensure-server":
            code, payload = ensure_wordbook_server(profile, port, dry_run=flag(args, "--dry-run"))
        case _:
            return _json_contract_error(
                "INVALID_SIDE_PANEL_WORDBOOK_COMMAND",
                "unknown wordbook command",
            )
    _write_json(payload)
    return code


def _port_option(args: list[str]) -> int:
    raw_port = option(args, "--port")
    if raw_port is None:
        return DEFAULT_WORDBOOK_PORT
    try:
        return int(raw_port)
    except ValueError:
        return DEFAULT_WORDBOOK_PORT


def _required_option(args: list[str], flag: str) -> str:
    value = _option(args, flag)
    if value is None:
        return ""
    return value


def _option(args: list[str], flag: str) -> str | None:
    for index, arg in enumerate(args[:-1]):
        if arg == flag:
            return args[index + 1]
    return None


def _subcommand_at(args: list[str], index: int) -> str:
    if len(args) <= index:
        return ""
    return args[index]


def _json_contract_error(error_code: str, message: str) -> int:
    _write_json({"status": "ERROR", "error_code": error_code, "message": message})
    return 2


def _write_json(payload: JsonValue) -> None:
    _ = sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
