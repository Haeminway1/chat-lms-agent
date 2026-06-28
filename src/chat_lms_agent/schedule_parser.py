from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import argparse


class _SubparserGroup(Protocol):
    def add_parser(self, name: str) -> argparse.ArgumentParser: ...


def add_schedule_parser(subparsers: _SubparserGroup) -> None:
    schedule = subparsers.add_parser("schedule")
    schedule_sub = schedule.add_subparsers(dest="schedule_command", required=True)

    for name in ("plan", "register"):
        command = schedule_sub.add_parser(name)
        _add_plan_args(command)

    list_parser = schedule_sub.add_parser("list")
    _add_profile_args(list_parser)
    _ = list_parser.add_argument("--json", action="store_true")

    status = schedule_sub.add_parser("status")
    _ = status.add_argument("--id", required=True)
    _add_profile_args(status)
    _ = status.add_argument("--json", action="store_true")

    runs = schedule_sub.add_parser("runs")
    _add_profile_args(runs)
    _ = runs.add_argument("--json", action="store_true")

    remove = schedule_sub.add_parser("remove")
    _ = remove.add_argument("--name", required=True)
    _add_profile_args(remove)
    _ = remove.add_argument("--json", action="store_true")

    run_now = schedule_sub.add_parser("run-now")
    _ = run_now.add_argument("--id", required=True)
    _add_profile_args(run_now)
    _ = run_now.add_argument("--json", action="store_true")


def _add_plan_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--kind", required=True)
    _ = parser.add_argument("--name")
    _ = parser.add_argument("--id")
    _ = parser.add_argument("--target")
    _ = parser.add_argument("--command")
    _ = parser.add_argument("--from", dest="from_path")
    _ = parser.add_argument("--from-json")
    _ = parser.add_argument("--to")
    _ = parser.add_argument("--date")
    _ = parser.add_argument("--database")
    _ = parser.add_argument("--out-dir")
    _ = parser.add_argument("--source-key")
    _ = parser.add_argument("--classes")
    _ = parser.add_argument("--token-file")
    _ = parser.add_argument("--at", required=True)
    _ = parser.add_argument("--execute", action="store_true")
    _ = parser.add_argument("--unattended-execute", action="store_true")
    _add_profile_args(parser)
    _ = parser.add_argument("--json", action="store_true")


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--profile-root")
    _ = parser.add_argument("--profile")
