from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from chat_lms_agent.hosts import DESIGN_GENERATION_DEFAULT_ENGINE_ID

if TYPE_CHECKING:
    import argparse


class _SubparserGroup(Protocol):
    def add_parser(self, name: str) -> argparse.ArgumentParser: ...


def add_side_panel_parser(subparsers: _SubparserGroup) -> None:
    side_panel = subparsers.add_parser("side-panel")
    side_panel_sub = side_panel.add_subparsers(dest="side_panel_command", required=True)
    spec = side_panel_sub.add_parser("spec")
    _ = spec.add_argument("--json", action="store_true")
    _add_side_panel_block_parser(side_panel_sub)
    _add_side_panel_view_parser(side_panel_sub)
    _add_side_panel_payload_parser(side_panel_sub)
    _add_side_panel_design_parser(side_panel_sub)
    _add_wordbook_parser(side_panel_sub)
    _add_lesson_parser(side_panel_sub)


def _add_side_panel_block_parser(side_panel_sub: _SubparserGroup) -> None:
    block = side_panel_sub.add_parser("block")
    block_sub = block.add_subparsers(dest="side_panel_block_command", required=True)
    block_list = block_sub.add_parser("list")
    _ = block_list.add_argument("--json", action="store_true")
    _add_profile_args(block_list)
    block_scaffold = block_sub.add_parser("scaffold")
    _ = block_scaffold.add_argument("--from", dest="from_path", required=True)
    _ = block_scaffold.add_argument("--json", action="store_true")
    _add_profile_args(block_scaffold)
    block_preview = block_sub.add_parser("preview")
    _ = block_preview.add_argument("--id", required=True)
    _ = block_preview.add_argument("--sample", required=True)
    _ = block_preview.add_argument("--json", action="store_true")
    _add_profile_args(block_preview)
    for name in ("register", "promote", "deprecate", "explain"):
        block_verb = block_sub.add_parser(name)
        _ = block_verb.add_argument("--id", required=True)
        _ = block_verb.add_argument("--json", action="store_true")
        _add_profile_args(block_verb)
        if name == "promote":
            _ = block_verb.add_argument("--evidence")
        if name == "deprecate":
            _ = block_verb.add_argument("--report")


def _add_side_panel_view_parser(side_panel_sub: _SubparserGroup) -> None:
    view = side_panel_sub.add_parser("view")
    view_sub = view.add_subparsers(dest="side_panel_view_command", required=True)
    draft = view_sub.add_parser("draft")
    _ = draft.add_argument("--view", required=True)
    _ = draft.add_argument("--json", action="store_true")


def _add_side_panel_payload_parser(side_panel_sub: _SubparserGroup) -> None:
    payload = side_panel_sub.add_parser("payload")
    payload_sub = payload.add_subparsers(dest="side_panel_payload_command", required=True)
    validate = payload_sub.add_parser("validate")
    _ = validate.add_argument("--from", dest="from_path", required=True)
    _ = validate.add_argument("--json", action="store_true")


def _add_side_panel_design_parser(side_panel_sub: _SubparserGroup) -> None:
    design = side_panel_sub.add_parser("design")
    design_sub = design.add_subparsers(dest="side_panel_design_command", required=True)
    lint = design_sub.add_parser("lint")
    _ = lint.add_argument("--artifact", required=True)
    _ = lint.add_argument("--mode", choices=("panel", "fullscreen", "all"), default="all")
    _ = lint.add_argument("--json", action="store_true")
    verify = design_sub.add_parser("verify")
    _ = verify.add_argument("--artifact", required=True)
    _ = verify.add_argument("--view", required=True)
    _ = verify.add_argument("--mode", choices=("panel", "fullscreen", "all"), default="all")
    _ = verify.add_argument("--json", action="store_true")
    generate = design_sub.add_parser("generate")
    _ = generate.add_argument("--view", required=True)
    _ = generate.add_argument("--modes", default="panel,fullscreen")
    _ = generate.add_argument("--design-system")
    _ = generate.add_argument("--brief")
    _ = generate.add_argument("--engine", default=DESIGN_GENERATION_DEFAULT_ENGINE_ID)
    _ = generate.add_argument("--json", action="store_true")
    _add_profile_args(generate)
    systems = design_sub.add_parser("systems")
    systems_sub = systems.add_subparsers(dest="side_panel_design_systems_command", required=True)
    systems_list = systems_sub.add_parser("list")
    _ = systems_list.add_argument("--json", action="store_true")
    _add_profile_args(systems_list)


def _add_wordbook_parser(side_panel_sub: _SubparserGroup) -> None:
    wordbook = side_panel_sub.add_parser("wordbook")
    wordbook_sub = wordbook.add_subparsers(dest="side_panel_wordbook_command", required=True)
    open_plan = wordbook_sub.add_parser("open-plan")
    _ = open_plan.add_argument("--student", required=True)
    _ = open_plan.add_argument("--date")
    _ = open_plan.add_argument("--port")
    _ = open_plan.add_argument("--json", action="store_true")
    _add_profile_args(open_plan)
    ensure_server = wordbook_sub.add_parser("ensure-server")
    _ = ensure_server.add_argument("--port")
    _ = ensure_server.add_argument("--dry-run", action="store_true")
    _ = ensure_server.add_argument("--json", action="store_true")
    _add_profile_args(ensure_server)


def _add_lesson_parser(side_panel_sub: _SubparserGroup) -> None:
    lesson = side_panel_sub.add_parser("lesson")
    lesson_sub = lesson.add_subparsers(dest="side_panel_lesson_command", required=True)
    open_plan = lesson_sub.add_parser("open-plan")
    _ = open_plan.add_argument("--student", required=True)
    _ = open_plan.add_argument("--date")
    _ = open_plan.add_argument("--view", default="lesson_prep")
    _ = open_plan.add_argument("--port")
    _ = open_plan.add_argument("--json", action="store_true")
    _add_profile_args(open_plan)
    ensure_server = lesson_sub.add_parser("ensure-server")
    _ = ensure_server.add_argument("--port")
    _ = ensure_server.add_argument("--dry-run", action="store_true")
    _ = ensure_server.add_argument("--json", action="store_true")
    _add_profile_args(ensure_server)
    install_assets = lesson_sub.add_parser("install-assets")
    _ = install_assets.add_argument("--force", action="store_true")
    _ = install_assets.add_argument("--json", action="store_true")
    _add_profile_args(install_assets)


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--profile-root")
    _ = parser.add_argument("--profile")
