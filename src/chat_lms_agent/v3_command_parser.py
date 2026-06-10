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
    model = harness_sub.add_parser("model")
    model_sub = model.add_subparsers(dest="harness_model_command", required=True)
    resolve = model_sub.add_parser("resolve")
    _ = resolve.add_argument("--role", required=True)
    _ = resolve.add_argument("--json", action="store_true")
    _add_profile_args(resolve)
    for name in ("list", "validate"):
        verb = model_sub.add_parser(name)
        _ = verb.add_argument("--json", action="store_true")
        _add_profile_args(verb)
    qa = harness_sub.add_parser("qa")
    qa_sub = qa.add_subparsers(dest="harness_qa_command", required=True)
    consent = qa_sub.add_parser("consent")
    _ = consent.add_argument("--grant", action="store_true")
    _ = consent.add_argument("--deny", action="store_true")
    _ = consent.add_argument("--json", action="store_true")
    _add_profile_args(consent)
    for name in ("list", "clear"):
        qa_verb = qa_sub.add_parser(name)
        _ = qa_verb.add_argument("--json", action="store_true")
        _add_profile_args(qa_verb)


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
    for name in ("list", "show", "inspect", "export"):
        command = trace_sub.add_parser(name)
        if name in {"show", "inspect"}:
            _ = command.add_argument("--id", required=True)
        if name == "export":
            _ = command.add_argument("--format", choices=("trajectory",), required=True)
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
