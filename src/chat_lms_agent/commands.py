from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Sequence

from chat_lms_agent import __version__
from chat_lms_agent.command_parser import APP_NAME, CliArgumentError, build_parser
from chat_lms_agent.context import build_codex_context
from chat_lms_agent.doctor import build_doctor_report, report_to_jsonable
from chat_lms_agent.onboarding import result_to_jsonable, validate_answers
from chat_lms_agent.state import (
    JsonValue,
    MemoryPayload,
    ProfileState,
    load_memory,
    load_tools,
    redact_text,
    resolve_profile_state,
    save_memory,
)
from chat_lms_agent.tool_handlers import handle_tool

SUBCOMMAND_LENGTH: Final = 2


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not args or args in (["-h"], ["--help"]):
        parser.print_help(sys.stdout)
        return 0
    if args == ["--version"]:
        _ = sys.stdout.write(f"{APP_NAME} {__version__}\n")
        return 0
    try:
        _ = parser.parse_args(args)
    except CliArgumentError as error:
        return _argument_error(error.message, wants_json="--json" in args)
    return _dispatch(args, parser)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _dispatch(args: list[str], parser: argparse.ArgumentParser) -> int:
    handlers: dict[str, Callable[[list[str]], int]] = {
        "doctor": _doctor,
        "context": _context,
        "onboarding": _onboarding,
        "profile": _profile,
        "tool": lambda route_args: handle_tool(route_args, _repo_root()),
        "memory": _memory,
        "session": _session,
        "hook": _hook,
        "bootstrap": _bootstrap,
    }
    handler = handlers.get(args[0])
    if handler is None:
        parser.print_help(sys.stdout)
        return 0
    return handler(args)


def _argument_error(message: str, *, wants_json: bool) -> int:
    if wants_json:
        _write_json({"status": "ERROR", "error_code": "INVALID_ARGUMENT", "message": message})
    else:
        _ = sys.stderr.write(f"{message}\n")
    return 2


def _doctor(args: list[str]) -> int:
    del args
    report = build_doctor_report(_repo_root())
    payload = report_to_jsonable(report)
    checks: list[JsonValue] = [
        {
            "id": check["id"],
            "status": check["status"],
            "message_ko": check["message_ko"],
            "repair_action": check["repair_action"],
            "safe_to_auto_repair": check["safe_to_auto_repair"],
        }
        for check in payload["checks"]
    ]
    needs_approval: list[JsonValue] = []
    needs_approval.extend(payload["needs_approval"])
    repair_failed: list[JsonValue] = []
    repair_failed.extend(payload["repair_failed"])
    report_payload: dict[str, JsonValue] = {
        "status": payload["status"],
        "exit_code": payload["exit_code"],
        "checks": checks,
        "needs_approval": needs_approval,
        "repair_failed": repair_failed,
    }
    _write_json(report_payload)
    return report.exit_code


def _context(args: list[str]) -> int:
    profile_root, profile = _profile_options(args)
    _write_json(build_codex_context(_repo_root(), profile_root, profile))
    return 0


def _onboarding(args: list[str]) -> int:
    result = validate_answers(Path(_required_option(args, "--answers")))
    payload = result_to_jsonable(result)
    _write_json(
        {
            "status": payload["status"],
            "exit_code": payload["exit_code"],
            "message_ko": payload["message_ko"],
        },
    )
    return result.exit_code


def _profile(args: list[str]) -> int:
    profile = _resolve_or_write_error(args)
    if profile is None:
        return 4
    _write_json(
        {
            "status": "PASS",
            "profile_root": "<profile-root>",
            "state_dir": "<profile-root>/.chat-lms-state",
        },
    )
    return 0


def _memory(args: list[str]) -> int:
    profile = _resolve_or_write_error(args)
    if profile is None:
        return 4
    entries = load_memory(profile)
    if _subcommand(args) == "list":
        _write_json({"status": "PASS", "memory": [_memory_json(entry) for entry in entries]})
        return 0
    entry: MemoryPayload = {
        "key": _required_option(args, "--key"),
        "scope": _required_option(args, "--scope"),
        "text": redact_text(_required_option(args, "--text")),
    }
    next_entries = [item for item in entries if item["key"] != entry["key"]]
    next_entries.append(entry)
    save_memory(profile, sorted(next_entries, key=lambda item: item["key"]))
    _write_json({"status": "PASS", "memory": _memory_json(entry)})
    return 0


def _session(args: list[str]) -> int:
    profile = _resolve_or_write_error(args)
    if profile is None:
        return 4
    return _write_closeout(profile)


def _hook(args: list[str]) -> int:
    profile = _resolve_or_write_error(args)
    if profile is None:
        return 4
    if _subcommand(args) == "stop":
        return _write_closeout(profile)
    profile_root, profile_name = _profile_options(args)
    context = build_codex_context(_repo_root(), profile_root, profile_name)
    _write_json(
        {
            "hookSpecificOutput": {
                "hookEventName": _subcommand(args),
                "additionalContext": json.dumps(context, ensure_ascii=False, sort_keys=True),
            },
        },
    )
    return 0


def _bootstrap(args: list[str]) -> int:
    del args
    actions: list[JsonValue] = ["doctor", "hooks", "profile"]
    _write_json({"status": "PASS", "actions": actions})
    return 0


def _write_closeout(profile: ProfileState) -> int:
    tools = [tool for tool in load_tools(profile) if tool["status"] == "active"]
    memory_keys = {entry["key"] for entry in load_memory(profile)}
    missing = [
        f"tool:{tool['name']}"
        for tool in tools
        if f"tool:{tool['name']}" not in memory_keys
    ]
    if missing:
        missing_memory: list[JsonValue] = []
        missing_memory.extend(missing)
        _write_json({"status": "BLOCKED", "missing_memory": missing_memory})
        return 5
    _write_json({"status": "PASS", "missing_memory": []})
    return 0


def _resolve_or_write_error(args: list[str]) -> ProfileState | None:
    profile_root, profile = _profile_options(args)
    profile_state = resolve_profile_state(_repo_root(), profile_root, profile)
    if isinstance(profile_state, str):
        _write_json(
            {
                "status": "UNSAFE",
                "error_code": profile_state,
                "message": "runtime profile state cannot use the public repository root",
            },
        )
        return None
    return profile_state


def _profile_options(args: list[str]) -> tuple[str | None, str | None]:
    return _option(args, "--profile-root"), _option(args, "--profile")


def _subcommand(args: list[str]) -> str:
    if len(args) < SUBCOMMAND_LENGTH:
        return ""
    return args[1]


def _required_option(args: list[str], flag: str) -> str:
    value = _option(args, flag)
    if value is None:
        message = "missing required argument: " + flag
        raise CliArgumentError(message)
    return value


def _option(args: list[str], flag: str) -> str | None:
    for index, arg in enumerate(args[:-1]):
        if arg == flag:
            return args[index + 1]
    return None


def _memory_json(entry: MemoryPayload) -> dict[str, JsonValue]:
    return {
        "key": entry["key"],
        "scope": entry["scope"],
        "text": entry["text"],
    }


def _write_json(payload: JsonValue) -> None:
    _ = sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
