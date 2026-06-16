from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import argparse


class _SubparserGroup(Protocol):
    def add_parser(self, name: str) -> argparse.ArgumentParser: ...


def add_write_action_parser(subparsers: _SubparserGroup) -> None:
    write_action = subparsers.add_parser("write-action")
    action_sub = write_action.add_subparsers(dest="write_action_command", required=True)

    list_parser = action_sub.add_parser("list")
    _ = list_parser.add_argument("--json", action="store_true")
    _add_profile_args(list_parser)

    explain = action_sub.add_parser("explain")
    _ = explain.add_argument("--id", required=True)
    _ = explain.add_argument("--json", action="store_true")
    _add_profile_args(explain)

    for name in ("plan", "apply"):
        command = action_sub.add_parser(name)
        _ = command.add_argument("--id", required=True)
        _ = command.add_argument("--from", dest="from_path", required=True)
        _ = command.add_argument("--json", action="store_true")
        _add_profile_args(command)

    roster = action_sub.add_parser("roster")
    _ = roster.add_argument("--class-code", required=True)
    _ = roster.add_argument("--json", action="store_true")
    _add_profile_args(roster)

    doctor = action_sub.add_parser("doctor")
    _ = doctor.add_argument("--json", action="store_true")
    _add_profile_args(doctor)


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--profile-root")
    _ = parser.add_argument("--profile")
