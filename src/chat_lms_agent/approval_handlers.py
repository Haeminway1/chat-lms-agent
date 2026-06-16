from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Protocol

from chat_lms_agent.approvals import (
    approve_request,
    deny_request,
    list_approvals,
    show_approval,
)
from chat_lms_agent.cli_io import (
    option,
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import ProfileState


class _ConfirmationStream(Protocol):
    """The minimal terminal surface the approve gate needs."""

    def isatty(self) -> bool: ...

    def readline(self) -> str: ...


def handle_approval(
    args: list[str],
    repo_root: Path,
    stdin: _ConfirmationStream | None = None,
) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    command = subcommand(args)
    if command == "list":
        write_json(list_approvals(profile))
        return 0
    if command == "show":
        code, payload = show_approval(profile, _required_approval_id(args))
        write_json(payload)
        return code
    if command == "approve":
        return _handle_approve(args, profile, stdin if stdin is not None else sys.stdin)
    if command == "deny":
        code, payload = deny_request(
            profile,
            _required_approval_id(args),
            required_option(args, "--actor"),
        )
        write_json(payload)
        return code
    write_json({"status": "ERROR", "error_code": "UNKNOWN_APPROVAL_COMMAND"})
    return 2


def _required_approval_id(args: list[str]) -> str:
    return option(args, "--approval-id") or required_option(args, "--id")


def _handle_approve(
    args: list[str],
    profile: ProfileState,
    stream: _ConfirmationStream,
) -> int:
    approval_id = _required_approval_id(args)
    if not stream.isatty():
        write_json(
            {
                "status": "BLOCKED",
                "error_code": "APPROVAL_REQUIRES_INTERACTIVE",
                "approval_id": approval_id,
                "message_ko": (
                    "승인은 교사가 직접 연 터미널에서만 가능합니다. "
                    "PowerShell 창에서 같은 명령을 실행해 주세요."
                ),
            },
        )
        return 5
    _ = sys.stderr.write(f"승인 ID를 입력해 확인하세요 [{approval_id}]: ")
    _ = sys.stderr.flush()
    typed = stream.readline().strip()
    if typed != approval_id:
        write_json(
            {
                "status": "BLOCKED",
                "error_code": "APPROVAL_CONFIRMATION_MISMATCH",
                "approval_id": approval_id,
                "message_ko": "입력한 승인 ID가 일치하지 않아 승인하지 않았습니다.",
            },
        )
        return 5
    code, payload = approve_request(profile, approval_id, required_option(args, "--actor"))
    write_json(payload)
    return code
