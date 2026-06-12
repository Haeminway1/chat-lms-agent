from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent.cli_io import option, profile_state_or_error, required_option
from chat_lms_agent.side_panel_design_generate import (
    DesignGenerateRequest,
    generate_side_panel_design,
    parse_generate_modes,
)
from chat_lms_agent.side_panel_design_lint import LintMode, side_panel_design_lint
from chat_lms_agent.side_panel_design_systems import design_systems_list_json
from chat_lms_agent.side_panel_design_verify import side_panel_design_verify

if TYPE_CHECKING:
    from chat_lms_agent.side_panel_design_verify_contract import VerifyMode
    from chat_lms_agent.state import JsonValue


def side_panel_design_command(args: list[str], repo_root: Path) -> tuple[int, dict[str, JsonValue]]:
    route = _subcommand_at(args, 2)
    match route:
        case "lint":
            mode = _lint_mode(option(args, "--mode"))
            artifact_path = Path(required_option(args, "--artifact"))
            return side_panel_design_lint(artifact_path, mode)
        case "verify":
            mode = _verify_mode(option(args, "--mode"))
            artifact_path = Path(required_option(args, "--artifact"))
            return side_panel_design_verify(artifact_path, required_option(args, "--view"), mode)
        case "systems":
            return _side_panel_design_systems(args, repo_root)
        case "generate":
            return _side_panel_design_generate(args, repo_root)
        case _:
            return 2, {
                "status": "ERROR",
                "error_code": "INVALID_SIDE_PANEL_DESIGN_COMMAND",
                "message": "unknown design command",
            }


def _side_panel_design_systems(
    args: list[str],
    repo_root: Path,
) -> tuple[int, dict[str, JsonValue]]:
    route = _subcommand_at(args, 3)
    if route != "list":
        return 2, {
            "status": "ERROR",
            "error_code": "INVALID_SIDE_PANEL_DESIGN_SYSTEMS_COMMAND",
            "message": "unknown design systems command",
        }
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4, {"status": "ERROR", "error_code": "INVALID_PROFILE"}
    return 0, design_systems_list_json(profile.repo_root, profile)


def _side_panel_design_generate(
    args: list[str],
    repo_root: Path,
) -> tuple[int, dict[str, JsonValue]]:
    if option(args, "--profile-root") is None and option(args, "--profile") is None:
        return 2, {
            "status": "ERROR",
            "error_code": "MISSING_PROFILE_ROOT",
            "message": "side-panel design generate requires --profile-root",
        }
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4, {"status": "ERROR", "error_code": "INVALID_PROFILE"}
    modes = parse_generate_modes(option(args, "--modes"))
    if modes is None:
        return 2, {
            "status": "ERROR",
            "error_code": "INVALID_DESIGN_MODES",
            "message": "--modes must be panel or panel,fullscreen",
        }
    return generate_side_panel_design(
        profile,
        DesignGenerateRequest(
            view=required_option(args, "--view"),
            modes=modes,
            design_system_id=option(args, "--design-system"),
            brief=option(args, "--brief"),
            engine_id=option(args, "--engine"),
        ),
    )


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


def _verify_mode(raw_mode: str | None) -> VerifyMode:
    match raw_mode:
        case "panel":
            return "panel"
        case "fullscreen":
            return "fullscreen"
        case "all" | None:
            return "all"
        case _:
            return "all"


def _subcommand_at(args: list[str], index: int) -> str:
    if len(args) <= index:
        return ""
    return args[index]
