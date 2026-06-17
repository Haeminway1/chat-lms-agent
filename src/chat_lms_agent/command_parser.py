from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Final, NoReturn, Protocol, override

from chat_lms_agent.academy_db_parser import add_academy_db_parser
from chat_lms_agent.agent_tools_parser import add_agent_tools_parser
from chat_lms_agent.integration_command_parser import add_integration_parsers
from chat_lms_agent.lifecycle_parser import add_memory_parser, add_session_parser
from chat_lms_agent.shortcut_parser import add_shortcut_parser
from chat_lms_agent.side_panel_parser import add_side_panel_parser
from chat_lms_agent.v3_command_parser import add_v3_parsers
from chat_lms_agent.write_action_parser import add_write_action_parser

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
    add_agent_tools_parser(subparsers)
    _add_skills_parser(subparsers)
    add_memory_parser(subparsers)
    add_session_parser(subparsers)
    _add_hook_parser(subparsers)
    add_shortcut_parser(subparsers)
    add_side_panel_parser(subparsers)
    add_academy_db_parser(subparsers)
    add_write_action_parser(subparsers)
    add_integration_parsers(subparsers)
    add_v3_parsers(subparsers)
    _add_goal_parser(subparsers)
    _add_session_log_parser(subparsers)
    _add_bootstrap_parser(subparsers)
    return parser


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
    for flag_name in ("--name", "--kind", "--summary"):
        _ = draft.add_argument(flag_name, required=True)
    _ = draft.add_argument("--command")
    _ = draft.add_argument("--template")
    _ = draft.add_argument("--json", action="store_true")
    _add_profile_args(draft)


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


def _add_session_log_parser(subparsers: _SubparserGroup) -> None:
    session_log = subparsers.add_parser("session-log")
    session_log_sub = session_log.add_subparsers(dest="session_log_command", required=True)
    for name in ("ingest", "list", "status", "enable", "disable"):
        command = session_log_sub.add_parser(name)
        if name == "ingest":
            _ = command.add_argument("--transcript-home")
        _ = command.add_argument("--json", action="store_true")
        _add_profile_args(command)
    for name in ("show", "export"):
        command = session_log_sub.add_parser(name)
        _ = command.add_argument("--session-id", required=True)
        _ = command.add_argument("--reveal", action="store_true")
        _ = command.add_argument("--json", action="store_true")
        _add_profile_args(command)


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
