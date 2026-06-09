from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import argparse


class _SubparserGroup(Protocol):
    def add_parser(self, name: str) -> argparse.ArgumentParser: ...


def add_memory_parser(subparsers: _SubparserGroup) -> None:
    memory = subparsers.add_parser("memory")
    memory_sub = memory.add_subparsers(dest="memory_command", required=True)
    upsert = memory_sub.add_parser("upsert")
    for flag in ("--key", "--scope", "--text"):
        _ = upsert.add_argument(flag, required=True)
    _ = upsert.add_argument("--json", action="store_true")
    _add_profile_args(upsert)
    for name in ("list", "compact", "levels"):
        command = memory_sub.add_parser(name)
        _ = command.add_argument("--json", action="store_true")
        _add_profile_args(command)
    archive = memory_sub.add_parser("archive")
    _ = archive.add_argument("--key", required=True)
    _ = archive.add_argument("--json", action="store_true")
    _add_profile_args(archive)
    verify = memory_sub.add_parser("verify")
    _ = verify.add_argument("--changed-files")
    _ = verify.add_argument("--for", dest="reason")
    _ = verify.add_argument("--json", action="store_true")
    _add_profile_args(verify)
    draft = memory_sub.add_parser("draft")
    _ = draft.add_argument("--changed-files")
    _ = draft.add_argument("--for", dest="reason")
    _ = draft.add_argument("--out")
    _ = draft.add_argument("--json", action="store_true")
    _add_profile_args(draft)
    apply_draft = memory_sub.add_parser("apply-draft")
    _ = apply_draft.add_argument("--from", dest="from_path", required=True)
    _ = apply_draft.add_argument("--json", action="store_true")
    _add_profile_args(apply_draft)


def add_session_parser(subparsers: _SubparserGroup) -> None:
    session = subparsers.add_parser("session")
    session_sub = session.add_subparsers(dest="session_command", required=True)
    closeout = session_sub.add_parser("closeout")
    _ = closeout.add_argument("--verify-memory", action="store_true")
    _ = closeout.add_argument("--json", action="store_true")
    _add_profile_args(closeout)
    summarize = session_sub.add_parser("summarize")
    _ = summarize.add_argument("--json", action="store_true")
    _add_profile_args(summarize)


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--profile-root")
    _ = parser.add_argument("--profile")
