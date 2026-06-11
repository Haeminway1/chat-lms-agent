from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

from chat_lms_agent.command_parser import CliArgumentError
from chat_lms_agent.state import JsonValue, ProfileState, resolve_profile_state

SUBCOMMAND_LENGTH: Final = 2


def write_json(payload: JsonValue) -> None:
    line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
    try:
        _ = sys.stdout.write(line)
    except UnicodeEncodeError:
        # A legacy console codepage (e.g. cp949) cannot encode every
        # character; degrade the echo instead of crashing after the
        # operation already succeeded.
        encoding = sys.stdout.encoding or "utf-8"
        _ = sys.stdout.write(line.encode(encoding, errors="replace").decode(encoding))


def argument_error(message: str, *, wants_json: bool) -> int:
    if wants_json:
        write_json({"status": "ERROR", "error_code": "INVALID_ARGUMENT", "message": message})
    else:
        _ = sys.stderr.write(f"{message}\n")
    return 2


def profile_state_or_error(args: list[str], repo_root: Path) -> ProfileState | None:
    profile_root, profile = profile_options(args)
    profile_state = resolve_profile_state(repo_root, profile_root, profile)
    if isinstance(profile_state, str):
        write_json(
            {
                "status": "UNSAFE",
                "error_code": profile_state,
                "message": "runtime profile state cannot use the public repository root",
            },
        )
        return None
    return profile_state


def profile_options(args: list[str]) -> tuple[str | None, str | None]:
    return option(args, "--profile-root"), option(args, "--profile")


def subcommand(args: list[str]) -> str:
    if len(args) < SUBCOMMAND_LENGTH:
        return ""
    return args[1]


def required_option(args: list[str], flag: str) -> str:
    value = option(args, flag)
    if value is None:
        message = "missing required argument: " + flag
        raise CliArgumentError(message)
    return value


def option(args: list[str], flag: str) -> str | None:
    for index, arg in enumerate(args[:-1]):
        if arg == flag:
            return args[index + 1]
    return None


def flag(args: list[str], name: str) -> bool:
    return name in args
