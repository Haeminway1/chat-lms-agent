from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Final, NoReturn, Protocol, override

from chat_lms_agent.academy_db_parser import add_academy_db_parser
from chat_lms_agent.lifecycle_parser import add_memory_parser, add_session_parser
from chat_lms_agent.v3_command_parser import add_v3_parsers

APP_NAME: Final = "chat-lms-agent"


@dataclass(frozen=True, slots=True)
class CliArgumentError(Exception):
    message: str


class _SubparserGroup(Protocol):
    def add_parser(self, name: str) -> argparse.ArgumentParser: ...


class _HarnessParser(argparse.ArgumentParser):
    @override
    def error(self, message: str) -> NoReturn:
        raise CliArgumentError(message)


def build_parser() -> argparse.ArgumentParser:
    parser = _HarnessParser(
        prog=APP_NAME,
        description="Public-safe local teacher assistant toolkit.",
        allow_abbrev=False,
    )
    _ = parser.add_argument("--version", action="store_true")
    subparsers = parser.add_subparsers(dest="main_command")
    _add_doctor_parser(subparsers)
    _add_context_parser(subparsers)
    _add_onboarding_parser(subparsers)
    _add_profile_parser(subparsers)
    _add_tool_parser(subparsers)
    _add_agent_tools_parser(subparsers)
    _add_skills_parser(subparsers)
    add_memory_parser(subparsers)
    add_session_parser(subparsers)
    _add_hook_parser(subparsers)
    _add_side_panel_parser(subparsers)
    add_academy_db_parser(subparsers)
    _add_classcard_parser(subparsers)
    add_v3_parsers(subparsers)
    _add_goal_parser(subparsers)
    _add_bootstrap_parser(subparsers)
    return parser


def _add_classcard_parser(subparsers: _SubparserGroup) -> None:
    classcard = subparsers.add_parser("classcard")
    sub = classcard.add_subparsers(dest="classcard_command", required=True)
    login = sub.add_parser("login")
    _ = login.add_argument("--username")
    _ = login.add_argument("--password")
    _ = login.add_argument("--json", action="store_true")
    direct = sub.add_parser("direct-upload")
    _ = direct.add_argument("--checkpoint", required=True)
    _ = direct.add_argument("--class-url", required=True)
    _ = direct.add_argument("--credentials")
    _ = direct.add_argument("--profile-dir")
    _ = direct.add_argument("--json", action="store_true")
    repair = sub.add_parser("direct-repair-audio")
    _ = repair.add_argument("--set-id", required=True)
    _ = repair.add_argument("--credentials")
    _ = repair.add_argument("--profile-dir")
    _ = repair.add_argument("--json", action="store_true")
    # DB-integrated flow is recognized but reports Phase-B-not-wired in the
    # handler (rather than an opaque parser rejection).
    for name in ("upload", "recover", "verify"):
        phase_b = sub.add_parser(name)
        _ = phase_b.add_argument("--student")
        _ = phase_b.add_argument("--class-url")
        _ = phase_b.add_argument("--checkpoint")
        _ = phase_b.add_argument("--json", action="store_true")
        _add_profile_args(phase_b)


def _add_doctor_parser(subparsers: _SubparserGroup) -> None:
    doctor = subparsers.add_parser("doctor")
    _ = doctor.add_argument("--repair", action="store_true")
    _ = doctor.add_argument("--json", action="store_true")
    _add_profile_args(doctor)


def _add_context_parser(subparsers: _SubparserGroup) -> None:
    context = subparsers.add_parser("context")
    context_sub = context.add_subparsers(dest="context_command", required=True)
    hydrate = context_sub.add_parser("hydrate")
    _ = hydrate.add_argument("--for-codex", action="store_true", dest="for_codex")
    _ = hydrate.add_argument("--for-host", action="store_true", dest="for_host")
    _ = hydrate.add_argument("--json", action="store_true")
    _add_profile_args(hydrate)
    map_parser = context_sub.add_parser("map")
    map_sub = map_parser.add_subparsers(dest="context_map_command", required=True)
    for name in ("build", "show"):
        command = map_sub.add_parser(name)
        _ = command.add_argument("--json", action="store_true")
        _add_profile_args(command)
    offload = context_sub.add_parser("offload")
    offload_sub = offload.add_subparsers(dest="context_offload_command", required=True)
    put = offload_sub.add_parser("put")
    _ = put.add_argument("--kind", required=True)
    _ = put.add_argument("--from", dest="from_path", required=True)
    _ = put.add_argument("--json", action="store_true")
    _add_profile_args(put)
    get = offload_sub.add_parser("get")
    _ = get.add_argument("--ref", required=True)
    _ = get.add_argument("--reveal", action="store_true")
    _ = get.add_argument("--json", action="store_true")
    _add_profile_args(get)
    budget = context_sub.add_parser("budget")
    budget_sub = budget.add_subparsers(dest="context_budget_command", required=True)
    show = budget_sub.add_parser("show")
    _ = show.add_argument("--json", action="store_true")
    _add_profile_args(show)


def _add_onboarding_parser(subparsers: _SubparserGroup) -> None:
    onboarding = subparsers.add_parser("onboarding")
    onboarding_sub = onboarding.add_subparsers(dest="onboarding_command", required=True)
    start = onboarding_sub.add_parser("start")
    _ = start.add_argument("--mode")
    _ = start.add_argument("--answers", required=True)
    _ = start.add_argument("--dry-run", action="store_true")
    _ = start.add_argument("--json", action="store_true")


def _add_profile_parser(subparsers: _SubparserGroup) -> None:
    profile = subparsers.add_parser("profile")
    profile_sub = profile.add_subparsers(dest="profile_command", required=True)
    inspect = profile_sub.add_parser("inspect")
    _ = inspect.add_argument("--json", action="store_true")
    _add_profile_args(inspect)


def _add_tool_parser(subparsers: _SubparserGroup) -> None:
    tool = subparsers.add_parser("tool")
    tool_sub = tool.add_subparsers(dest="tool_command", required=True)
    for name in ("list", "show", "activate", "deprecate"):
        tool_cmd = tool_sub.add_parser(name)
        _ = tool_cmd.add_argument("--json", action="store_true")
        if name != "list":
            _ = tool_cmd.add_argument("--name", required=True)
        _add_profile_args(tool_cmd)
    draft = tool_sub.add_parser("draft")
    for flag in ("--name", "--kind", "--summary"):
        _ = draft.add_argument(flag, required=True)
    _ = draft.add_argument("--command")
    _ = draft.add_argument("--template")
    _ = draft.add_argument("--json", action="store_true")
    _add_profile_args(draft)


def _add_agent_tools_parser(subparsers: _SubparserGroup) -> None:
    agent_tools = subparsers.add_parser("agent-tools")
    agent_tools_sub = agent_tools.add_subparsers(dest="agent_tools_command", required=True)
    list_tools = agent_tools_sub.add_parser("list")
    _ = list_tools.add_argument("--json", action="store_true")
    validate = agent_tools_sub.add_parser("validate")
    _ = validate.add_argument("--from", dest="from_path", required=True)
    _ = validate.add_argument("--json", action="store_true")
    reuse_check = agent_tools_sub.add_parser("reuse-check")
    _ = reuse_check.add_argument("--intent", required=True)
    _ = reuse_check.add_argument("--json", action="store_true")
    _add_profile_args(reuse_check)
    prompt_check = agent_tools_sub.add_parser("prompt-check")
    _ = prompt_check.add_argument("--prompt", required=True)
    _ = prompt_check.add_argument("--json", action="store_true")
    _add_profile_args(prompt_check)
    for name in ("scaffold", "register", "promote", "deprecate", "explain", "doctor"):
        command = agent_tools_sub.add_parser(name)
        _ = command.add_argument("--json", action="store_true")
        _add_profile_args(command)
        if name == "scaffold":
            _ = command.add_argument("--from", dest="from_path", required=True)
        if name in {"register", "promote", "deprecate", "explain"}:
            _ = command.add_argument("--id", required=True)
        if name == "promote":
            _ = command.add_argument("--evidence")


def _add_skills_parser(subparsers: _SubparserGroup) -> None:
    skills = subparsers.add_parser("skills")
    skills_sub = skills.add_subparsers(dest="skills_command", required=True)
    for name in ("list", "validate"):
        command = skills_sub.add_parser(name)
        _ = command.add_argument("--root")
        _ = command.add_argument("--json", action="store_true")


def _add_hook_parser(subparsers: _SubparserGroup) -> None:
    hook = subparsers.add_parser("hook")
    hook_sub = hook.add_subparsers(dest="hook_command", required=True)
    for name in (
        "session-start",
        "user-prompt-submit",
        "pre-tool-use",
        "post-tool-use",
        "post-compact",
        "stop",
    ):
        hook_cmd = hook_sub.add_parser(name)
        _ = hook_cmd.add_argument("--verify-memory", action="store_true")
        _ = hook_cmd.add_argument("--changed-files")
        _ = hook_cmd.add_argument("--memory-updated", action="store_true")
        _ = hook_cmd.add_argument("--json", action="store_true")
        _add_profile_args(hook_cmd)


def _add_side_panel_parser(subparsers: _SubparserGroup) -> None:
    side_panel = subparsers.add_parser("side-panel")
    side_panel_sub = side_panel.add_subparsers(dest="side_panel_command", required=True)
    spec = side_panel_sub.add_parser("spec")
    _ = spec.add_argument("--json", action="store_true")
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
    view = side_panel_sub.add_parser("view")
    view_sub = view.add_subparsers(dest="side_panel_view_command", required=True)
    draft = view_sub.add_parser("draft")
    _ = draft.add_argument("--view", required=True)
    _ = draft.add_argument("--json", action="store_true")
    payload = side_panel_sub.add_parser("payload")
    payload_sub = payload.add_subparsers(dest="side_panel_payload_command", required=True)
    validate = payload_sub.add_parser("validate")
    _ = validate.add_argument("--from", dest="from_path", required=True)
    _ = validate.add_argument("--json", action="store_true")
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


def _add_bootstrap_parser(subparsers: _SubparserGroup) -> None:
    bootstrap = subparsers.add_parser("bootstrap")
    _ = bootstrap.add_argument("--json", action="store_true")
    bootstrap_sub = bootstrap.add_subparsers(dest="bootstrap_command", required=False)
    for name in ("plan", "apply", "sync-runtime"):
        command = bootstrap_sub.add_parser(name)
        _ = command.add_argument("--json", action="store_true")
        _add_profile_args(command)


def _add_goal_parser(subparsers: _SubparserGroup) -> None:
    goal = subparsers.add_parser("goal")
    goal_sub = goal.add_subparsers(dest="goal_command", required=True)
    status = goal_sub.add_parser("status")
    _ = status.add_argument("--json", action="store_true")
    _add_profile_args(status)
    verify = goal_sub.add_parser("verify")
    _ = verify.add_argument("--goal-id", required=True)
    _ = verify.add_argument("--json", action="store_true")
    _add_profile_args(verify)
    evidence = goal_sub.add_parser("evidence")
    evidence_sub = evidence.add_subparsers(dest="goal_evidence_command", required=True)
    add = evidence_sub.add_parser("add")
    _ = add.add_argument("--goal-id", required=True)
    _ = add.add_argument("--from", dest="from_path", required=True)
    _ = add.add_argument("--json", action="store_true")
    _add_profile_args(add)


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--profile-root")
    _ = parser.add_argument("--profile")
