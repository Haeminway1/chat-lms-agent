from __future__ import annotations

import subprocess
import webbrowser
from typing import TYPE_CHECKING

from chat_lms_agent.cli_io import (
    option,
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)
from chat_lms_agent.shortcuts import (
    BrowserOpener,
    CommandResult,
    CommandRunner,
    Shortcut,
    find_shortcut,
    last_non_empty_stdout_line,
    load_shortcuts,
    remove_shortcut,
    save_shortcut,
    shortcut_list_item,
    shortcut_to_json,
    validate_shortcut_fields,
)

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState


def handle_shortcut(
    args: list[str],
    repo_root: Path,
    *,
    command_runner: CommandRunner | None = None,
    browser_opener: BrowserOpener | None = None,
) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    runner = command_runner if command_runner is not None else _run_command
    opener = browser_opener if browser_opener is not None else webbrowser.open
    command = subcommand(args)
    match command:
        case "list":
            return _list(profile)
        case "add":
            return _add(args, profile)
        case "run":
            return _run(args, profile, runner, opener)
        case "remove":
            return _remove(args, profile)
        case _:
            write_json({"status": "ERROR", "error_code": "UNKNOWN_SHORTCUT_COMMAND"})
            return 2


def _list(profile: ProfileState) -> int:
    shortcuts, warnings = load_shortcuts(profile)
    shortcut_payloads: list[JsonValue] = [shortcut_list_item(shortcut) for shortcut in shortcuts]
    warning_payloads: list[JsonValue] = []
    warning_payloads.extend(warnings)
    write_json({"status": "PASS", "shortcuts": shortcut_payloads, "warnings": warning_payloads})
    return 0


def _add(args: list[str], profile: ProfileState) -> int:
    name = required_option(args, "--name")
    run = required_option(args, "--run")
    errors = validate_shortcut_fields(name, run)
    if errors:
        write_json({"status": "ERROR", "error_code": _validation_error_code(errors[0])})
        return 2
    description = option(args, "--description") or ""
    shortcut = Shortcut(
        name=name.strip(),
        run=run.strip(),
        description=description,
        open_browser="--open-browser" in args,
    )
    _ = save_shortcut(profile, shortcut)
    write_json({"status": "PASS", "shortcut": shortcut_to_json(shortcut)})
    return 0


def _run(
    args: list[str],
    profile: ProfileState,
    command_runner: CommandRunner,
    browser_opener: BrowserOpener,
) -> int:
    name = required_option(args, "--name").strip()
    if not name:
        write_json(
            {"status": "ERROR", "error_code": "INVALID_SHORTCUT", "errors": ["EMPTY_NAME"]},
        )
        return 2
    shortcut = find_shortcut(profile, name)
    if shortcut is None:
        write_json({"status": "ERROR", "error_code": "UNKNOWN_SHORTCUT", "name": name})
        return 2
    result = command_runner(shortcut.run)
    stdout_tail = _stdout_tail(result.stdout)
    payload: dict[str, JsonValue] = {
        "status": "PASS" if result.exit_code == 0 else "ERROR",
        "name": shortcut.name,
        "exit_code": result.exit_code,
        "stdout_tail": stdout_tail,
    }
    if shortcut.open_browser:
        url = last_non_empty_stdout_line(result.stdout)
        if url:
            _ = browser_opener(url)
            payload["url"] = url
    if result.exit_code != 0:
        payload["error_code"] = "SHORTCUT_COMMAND_FAILED"
    write_json(payload)
    return result.exit_code


def _remove(args: list[str], profile: ProfileState) -> int:
    name = required_option(args, "--name").strip()
    if not name:
        write_json(
            {"status": "ERROR", "error_code": "INVALID_SHORTCUT", "errors": ["EMPTY_NAME"]},
        )
        return 2
    if not remove_shortcut(profile, name):
        write_json({"status": "ERROR", "error_code": "UNKNOWN_SHORTCUT", "name": name})
        return 2
    write_json({"status": "PASS", "removed": name})
    return 0


def _run_command(command: str) -> CommandResult:
    # Shortcuts are user-authored shell command strings by contract.
    result = subprocess.run(  # noqa: S602
        command,
        shell=True,
        capture_output=True,
        check=False,
        text=True,
    )
    return CommandResult(
        exit_code=result.returncode,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def _validation_error_code(error: str) -> str:
    match error:
        case "EMPTY_NAME":
            return "EMPTY_SHORTCUT_NAME"
        case "EMPTY_RUN":
            return "EMPTY_SHORTCUT_RUN"
        case "INVALID_NAME":
            return "INVALID_SHORTCUT_NAME"
        case _:
            return error


def _stdout_tail(stdout: str) -> str:
    lines = [line for line in stdout.splitlines() if line.strip()]
    return "\n".join(lines[-20:])
