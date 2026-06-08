from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Final, NoReturn, Protocol, override

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
    _add_memory_parser(subparsers)
    _add_session_parser(subparsers)
    _add_hook_parser(subparsers)
    _ = subparsers.add_parser("bootstrap")
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
    _ = hydrate.add_argument("--json", action="store_true")
    _add_profile_args(hydrate)


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


def _add_memory_parser(subparsers: _SubparserGroup) -> None:
    memory = subparsers.add_parser("memory")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    upsert = memory_sub.add_parser("upsert")
    for flag in ("--key", "--scope", "--text"):
        _ = upsert.add_argument(flag, required=True)
    _ = upsert.add_argument("--json", action="store_true")
    _add_profile_args(upsert)
    list_memory = memory_sub.add_parser("list")
    _ = list_memory.add_argument("--json", action="store_true")
    _add_profile_args(list_memory)


def _add_session_parser(subparsers: _SubparserGroup) -> None:
    session = subparsers.add_parser("session")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    closeout = session_sub.add_parser("closeout")
    _ = closeout.add_argument("--verify-memory", action="store_true")
    _ = closeout.add_argument("--json", action="store_true")
    _add_profile_args(closeout)


def _add_hook_parser(subparsers: _SubparserGroup) -> None:
    hook = subparsers.add_parser("hook")
    hook_sub = hook.add_subparsers(dest="hook_command", required=True)
    for name in ("session-start", "user-prompt-submit", "post-tool-use", "post-compact", "stop"):
        hook_cmd = hook_sub.add_parser(name)
        _ = hook_cmd.add_argument("--verify-memory", action="store_true")
        _ = hook_cmd.add_argument("--json", action="store_true")
        _add_profile_args(hook_cmd)


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--profile-root")
    _ = parser.add_argument("--profile")
