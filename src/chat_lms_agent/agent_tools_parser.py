from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import argparse


class _SubparserGroup(Protocol):
    def add_parser(self, name: str) -> argparse.ArgumentParser: ...


def add_agent_tools_parser(subparsers: _SubparserGroup) -> None:
    agent_tools = subparsers.add_parser("agent-tools")
    agent_tools_sub = agent_tools.add_subparsers(dest="agent_tools_command", required=True)
    list_tools = agent_tools_sub.add_parser("list")
    _ = list_tools.add_argument("--json", action="store_true")
    validate = agent_tools_sub.add_parser("validate")
    _ = validate.add_argument("--from", dest="from_path", required=True)
    _ = validate.add_argument("--json", action="store_true")
    reuse_check = agent_tools_sub.add_parser("reuse-check")
    _ = reuse_check.add_argument("--intent", required=True)
    _ = reuse_check.add_argument("--json", action="store_true")
    _add_profile_args(reuse_check)
    prompt_check = agent_tools_sub.add_parser("prompt-check")
    _ = prompt_check.add_argument("--prompt", required=True)
    _ = prompt_check.add_argument("--json", action="store_true")
    _add_profile_args(prompt_check)
    route = agent_tools_sub.add_parser("route")
    route_sub = route.add_subparsers(dest="agent_tools_route_command", required=True)
    route_record = route_sub.add_parser("record")
    _ = route_record.add_argument("--route-id", required=True)
    _ = route_record.add_argument("--json", action="store_true")
    _add_profile_args(route_record)
    for name in ("scaffold", "register", "promote", "deprecate", "explain", "doctor"):
        command = agent_tools_sub.add_parser(name)
        _ = command.add_argument("--json", action="store_true")
        _add_profile_args(command)
        if name == "scaffold":
            _ = command.add_argument("--from", dest="from_path", required=True)
        if name in {"register", "promote", "deprecate", "explain"}:
            _ = command.add_argument("--id", required=True)
        if name == "promote":
            _ = command.add_argument("--evidence")


def _add_profile_args(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument("--profile-root")
    _ = parser.add_argument("--profile")
