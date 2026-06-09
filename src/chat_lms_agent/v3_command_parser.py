from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import argparse


class _SubparserGroup(Protocol):
    def add_parser(self, name: str) -> argparse.ArgumentParser: ...


def add_v3_parsers(subparsers: _SubparserGroup) -> None:
    _add_harness_parser(subparsers)
    _add_approval_parser(subparsers)
    _add_trace_parser(subparsers)
    _add_audit_parser(subparsers)


def _add_harness_parser(subparsers: _SubparserGroup) -> None:
    harness = subparsers.add_parser("harness")
    harness_sub = harness.add_subparsers(dest="harness_command", required=True)
    event = harness_sub.add_parser("event")
    event_sub = event.add_subparsers(dest="harness_event_command", required=True)
    normalize = event_sub.add_parser("normalize")
    _ = normalize.add_argument("--from", dest="from_path", required=True)
    _ = normalize.add_argument("--json", action="store_true")


def _add_approval_parser(subparsers: _SubparserGroup) -> None:
    approval = subparsers.add_parser("approval")
    approval_sub = approval.add_subparsers(dest="approval_command", required=True)
    for name in ("list", "show", "approve", "deny"):
        command = approval_sub.add_parser(name)
        if name != "list":
            _ = command.add_argument("--approval-id", "--id", dest="approval_id", required=True)
        if name in {"approve", "deny"}:
            _ = command.add_argument("--actor", required=True)
        _ = command.add_argument("--json", action="store_true")
        _add_profile_args(command)


def _add_trace_parser(subparsers: _SubparserGroup) -> None:
    trace = subparsers.add_parser("trace")
    trace_sub = trace.add_subparsers(dest="trace_command", required=True)
    for name in ("list", "show"):
        command = trace_sub.add_parser(name)
        if name == "show":
            _ = command.add_argument("--id", required=True)
        _ = command.add_argument("--json", action="store_true")
        _add_profile_args(command)


def _add_audit_parser(subparsers: _SubparserGroup) -> None:
    audit = subparsers.add_parser("audit")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)
    command = audit_sub.add_parser("list")
    _ = command.add_argument("--json", action="store_true")
    _add_profile_args(command)


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--profile-root")
    _ = parser.add_argument("--profile")
