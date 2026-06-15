from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import argparse


class _SubparserGroup(Protocol):
    def add_parser(self, name: str) -> argparse.ArgumentParser: ...


def add_shortcut_parser(subparsers: _SubparserGroup) -> None:
    shortcut = subparsers.add_parser("shortcut")
    shortcut_sub = shortcut.add_subparsers(dest="shortcut_command", required=True)
    list_parser = shortcut_sub.add_parser("list")
    _add_profile_args(list_parser)
    _ = list_parser.add_argument("--json", action="store_true")

    add = shortcut_sub.add_parser("add")
    _ = add.add_argument("--name", required=True)
    _ = add.add_argument("--run", required=True)
    _ = add.add_argument("--description")
    _ = add.add_argument("--open-browser", action="store_true")
    _add_profile_args(add)
    _ = add.add_argument("--json", action="store_true")

    run = shortcut_sub.add_parser("run")
    _ = run.add_argument("--name", required=True)
    _add_profile_args(run)
    _ = run.add_argument("--json", action="store_true")

    remove = shortcut_sub.add_parser("remove")
    _ = remove.add_argument("--name", required=True)
    _add_profile_args(remove)
    _ = remove.add_argument("--json", action="store_true")


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--profile-root")
    _ = parser.add_argument("--profile")
