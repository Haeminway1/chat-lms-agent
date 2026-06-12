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
from chat_lms_agent.side_panel_blocks import (
    BlockLifecycleState,
    active_profile_blocks,
    explain_block,
    open_block_ids,
    preview_block,
    scaffold_block,
    set_block_state,
)
from chat_lms_agent.side_panel_design_lint import LintMode, side_panel_design_lint
from chat_lms_agent.side_panel_design_systems import design_systems_list_json
from chat_lms_agent.side_panel_lesson import (
    DEFAULT_LESSON_PORT,
    ensure_lesson_server,
    install_lesson_assets,
    lesson_open_plan,
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
            code = 0
        case "block":
            code = _side_panel_block(args, repo_root)
        case "view":
            code = _side_panel_view(args)
        case "payload":
            code = _side_panel_payload(args)
        case "design":
            code = _side_panel_design(args)
        case "wordbook":
            code = _side_panel_wordbook(args, repo_root)
        case "lesson":
            code = _side_panel_lesson(args, repo_root)
        case _:
            code = _json_contract_error("INVALID_SIDE_PANEL_COMMAND", "unknown side-panel command")
    return code


def _side_panel_block(args: list[str], repo_root: Path) -> int:
    route = _subcommand_at(args, 2)
    if route == "list":
        return _block_list(args, repo_root)
    if route in {"scaffold", "register", "promote", "deprecate", "explain", "preview"}:
        return _block_lifecycle(args, route, repo_root)
    return _json_contract_error("INVALID_SIDE_PANEL_BLOCK_COMMAND", "unknown block command")


def _block_list(args: list[str], repo_root: Path) -> int:
    payload = side_panel_blocks_json()
    if option(args, "--profile-root") is not None or option(args, "--profile") is not None:
        profile = profile_state_or_error(args, repo_root)
        if profile is None:
            return 4
        payload["active_profile_blocks"] = active_profile_blocks(profile)
        payload["open_profile_blocks"] = list(open_block_ids(profile))
    _write_json(payload)
    return 0


def _block_lifecycle(args: list[str], route: str, repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    if route == "scaffold":
        code, payload = scaffold_block(profile, Path(required_option(args, "--from")))
    elif route == "preview":
        code, payload = preview_block(
            profile,
            required_option(args, "--id"),
            Path(required_option(args, "--sample")),
        )
    elif route == "explain":
        code, payload = explain_block(profile, required_option(args, "--id"))
    else:
        target: dict[str, BlockLifecycleState] = {
            "register": "registered",
            "promote": "active",
            "deprecate": "deprecated",
        }
        code, payload = set_block_state(
            profile,
            required_option(args, "--id"),
            target[route],
            evidence=option(args, "--evidence"),
            report=option(args, "--report"),
        )
    _write_json(payload)
    return code


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


def _side_panel_design(args: list[str]) -> int:
    route = _subcommand_at(args, 2)
    match route:
        case "lint":
            mode = _lint_mode(option(args, "--mode"))
            artifact_path = Path(_required_option(args, "--artifact"))
            status_code, payload = side_panel_design_lint(artifact_path, mode)
            _write_json(payload)
            return status_code
        case "systems":
            return _side_panel_design_systems(args)
        case _:
            return _json_contract_error(
                "INVALID_SIDE_PANEL_DESIGN_COMMAND",
                "unknown design command",
            )


def _side_panel_design_systems(args: list[str]) -> int:
    route = _subcommand_at(args, 3)
    if route != "list":
        return _json_contract_error(
            "INVALID_SIDE_PANEL_DESIGN_SYSTEMS_COMMAND",
            "unknown design systems command",
        )
    profile = profile_state_or_error(args, _repo_root_for_profile())
    if profile is None:
        return 4
    _write_json(design_systems_list_json(profile.repo_root, profile))
    return 0


def _repo_root_for_profile() -> Path:
    return Path(__file__).resolve().parents[2]


def _lint_mode(raw_mode: str | None) -> LintMode:
    match raw_mode:
        case "panel":
            return "panel"
        case "fullscreen":
            return "fullscreen"
        case "all" | None:
            return "all"
        case _:
            return "all"


def _side_panel_wordbook(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    route = _subcommand_at(args, 2)
    port = _port_option(args, DEFAULT_WORDBOOK_PORT)
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


def _side_panel_lesson(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    route = _subcommand_at(args, 2)
    port = _port_option(args, DEFAULT_LESSON_PORT)
    match route:
        case "open-plan":
            code, payload = lesson_open_plan(
                profile,
                required_option(args, "--student"),
                option(args, "--date"),
                option(args, "--view") or "lesson_prep",
                port,
            )
        case "ensure-server":
            code, payload = ensure_lesson_server(profile, port, dry_run=flag(args, "--dry-run"))
        case "install-assets":
            code, payload = install_lesson_assets(profile, force=flag(args, "--force"))
        case _:
            return _json_contract_error(
                "INVALID_SIDE_PANEL_LESSON_COMMAND",
                "unknown lesson command",
            )
    _write_json(payload)
    return code


def _port_option(args: list[str], default: int) -> int:
    raw_port = option(args, "--port")
    if raw_port is None:
        return default
    try:
        return int(raw_port)
    except ValueError:
        return default


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
