from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent.cli_io import (
    option,
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)
from chat_lms_agent.integration_modules import consume_outward_send, evaluate_outward_send
from chat_lms_agent.kakao_calibration import (
    KakaoCalibrationError,
    calibration_error_payload,
    load_calibration_pack,
)
from chat_lms_agent.kakao_core import (
    KakaoChatMessage,
    ingest_chat_history,
    load_chat_history,
    summarize_chat_history,
)
from chat_lms_agent.kakao_plan import KakaoPlanError, build_send_plan
from chat_lms_agent.kakao_send import run_kakao_send_sequence

if TYPE_CHECKING:
    from chat_lms_agent.kakao_channel_page import (
        KakaoChannelPage,
        KakaoChatPage,
    )
    from chat_lms_agent.state import JsonValue, ProfileState

CHAT_VERB_INDEX = 2


@dataclass(frozen=True, slots=True)
class KakaoCommandResult:
    exit_code: int
    payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class KakaoFriendSendRequest:
    recipient: str
    message: str
    approval_id: str | None
    checkpoint: Path


def handle_kakao(args: list[str], repo_root: Path) -> int:
    command = subcommand(args)
    handlers = {
        "status": lambda: _status(args, repo_root),
        "send-friend": lambda: _send_friend(args, repo_root),
        "chats": lambda: _chats(args, repo_root),
        "history": lambda: _history(args, repo_root),
        "summary": lambda: _summary(args, repo_root),
        "login": _login,
        "calibrate": lambda: _calibrate(args, repo_root),
    }
    handler = handlers.get(command)
    if handler is not None:
        return handler()
    write_json({"status": "ERROR", "error_code": "UNKNOWN_KAKAO_COMMAND"})
    return 2


def send_chat_reply(
    profile: ProfileState,
    *,
    contact_id: str,
    message: str,
    approval_id: str | None,
    page: KakaoChatPage | None = None,
) -> KakaoCommandResult:
    gate = evaluate_outward_send(
        profile,
        approval_id,
        kind="kakao_chat_reply",
        recipient=contact_id,
        summary=_message_summary(message),
        error_prefix="KAKAO",
    )
    if gate.decision != "proceed":
        return KakaoCommandResult(gate.exit_code, gate.payload or {})
    if page is None:
        calibration = load_calibration_pack(profile)
        if isinstance(calibration, KakaoCalibrationError):
            return KakaoCommandResult(2, calibration_error_payload(calibration))
        return KakaoCommandResult(2, _login_required_payload())
    page.send_chat_reply(contact_id, message)
    consume_outward_send(profile, gate)
    _ = ingest_chat_history(
        profile,
        contact_id=contact_id,
        messages=(
            KakaoChatMessage(
                message_id=f"outbound-{datetime.now(UTC).isoformat()}",
                direction="outbound",
                text=message,
                sent_at=datetime.now(UTC).isoformat(),
            ),
        ),
    )
    return KakaoCommandResult(0, {"status": "PASS", "contact_id": contact_id})


def _send_friend(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    message = _message_from_args(args)
    recipient = _friend_recipient(args)
    gate = evaluate_outward_send(
        profile,
        option(args, "--approval-id"),
        kind="kakao_friend_broadcast",
        recipient=recipient,
        summary=_message_summary(message),
        error_prefix="KAKAO",
    )
    if gate.decision != "proceed":
        write_json(gate.payload or {})
        return gate.exit_code
    calibration = load_calibration_pack(profile)
    if isinstance(calibration, KakaoCalibrationError):
        write_json(calibration_error_payload(calibration))
        return 2
    max_raw = option(args, "--max")
    try:
        _ = build_send_plan(
            recipient=recipient,
            message=message,
            max_parts_per_run=int(max_raw) if max_raw else 20,
        )
    except KakaoPlanError as error:
        write_json({"status": "ERROR", "error_code": error.error_code, "message": error.message})
        return 2
    write_json(_login_required_payload())
    return 2


def send_friend_with_page(
    profile: ProfileState,
    *,
    request: KakaoFriendSendRequest,
    page: KakaoChannelPage,
) -> KakaoCommandResult:
    gate = evaluate_outward_send(
        profile,
        request.approval_id,
        kind="kakao_friend_broadcast",
        recipient=request.recipient,
        summary=_message_summary(request.message),
        error_prefix="KAKAO",
    )
    if gate.decision != "proceed":
        return KakaoCommandResult(gate.exit_code, gate.payload or {})
    plan = build_send_plan(recipient=request.recipient, message=request.message)
    result = run_kakao_send_sequence(plan, page, request.checkpoint)
    if result.status != "completed":
        return KakaoCommandResult(1, {"status": "ERROR", "error_code": "KAKAO_SEND_FAILED"})
    consume_outward_send(profile, gate)
    return KakaoCommandResult(
        0,
        {"status": "PASS", "completed_parts": len(result.completed_part_indexes)},
    )


def _status(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    calibration = load_calibration_pack(profile)
    calibrated = not isinstance(calibration, KakaoCalibrationError)
    quota_ceiling = calibration.free_quota_ceiling if calibrated else None
    write_json(
        {
            "status": "PASS",
            "kakao": {
                "login_state": "unknown",
                "calibration_state": "ready" if calibrated else "required",
                "month_to_date_sent": 0,
                "free_quota_ceiling": quota_ceiling,
                "last_inbound_at": None,
            },
        },
    )
    return 0


def _chats(args: list[str], repo_root: Path) -> int:
    verb = args[CHAT_VERB_INDEX] if len(args) > CHAT_VERB_INDEX else ""
    if verb == "reply":
        profile = profile_state_or_error(args, repo_root)
        if profile is None:
            return 4
        result = send_chat_reply(
            profile,
            contact_id=required_option(args, "--contact"),
            message=required_option(args, "--message"),
            approval_id=option(args, "--approval-id"),
        )
        write_json(result.payload)
        return result.exit_code
    if verb == "pull":
        profile = profile_state_or_error(args, repo_root)
        if profile is None:
            return 4
        calibration = load_calibration_pack(profile)
        if isinstance(calibration, KakaoCalibrationError):
            write_json(calibration_error_payload(calibration))
            return 2
        write_json(_login_required_payload())
        return 2
    write_json({"status": "ERROR", "error_code": "UNKNOWN_KAKAO_COMMAND"})
    return 2


def _history(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    contact_id = required_option(args, "--contact")
    messages: list[JsonValue] = [
        {
            "message_id": message.message_id,
            "direction": message.direction,
            "text": message.text,
            "sent_at": message.sent_at,
        }
        for message in load_chat_history(profile, contact_id=contact_id)
    ]
    write_json({"status": "PASS", "contact_id": contact_id, "messages": messages})
    return 0


def _summary(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    contact_id = required_option(args, "--contact")
    summary = summarize_chat_history(profile, contact_id=contact_id)
    write_json(
        {
            "status": "PASS",
            "contact_id": summary.contact_id,
            "message_count": summary.message_count,
            "inbound_count": summary.inbound_count,
            "outbound_count": summary.outbound_count,
            "last_message_text": summary.last_message_text,
        },
    )
    return 0


def _login() -> int:
    write_json(
        {
            "status": "NEEDS_INPUT",
            "error_code": "KAKAO_LOGIN_REQUIRED",
            "message_ko": "최초 1회 카카오 채널 관리자센터 로그인이 필요합니다.",
        },
    )
    return 2


def _calibrate(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    write_json(
        {
            "status": "NEEDS_INPUT",
            "error_code": "KAKAO_CALIBRATION_REQUIRED",
            "calibration_pack": "<profile-root>/.chat-lms-state/kakao/calibration.json",
        },
    )
    return 2


def _message_from_args(args: list[str]) -> str:
    body_file = option(args, "--body-file")
    if body_file is not None:
        return Path(body_file).read_text(encoding="utf-8")
    return required_option(args, "--message")


def _friend_recipient(args: list[str]) -> str:
    group = option(args, "--group")
    if group is not None:
        return f"friend-group:{group}"
    return "channel-friends"


def _message_summary(message: str) -> str:
    compact = " ".join(message.split())
    return compact[:60] if compact else "<empty>"


def _login_required_payload() -> dict[str, JsonValue]:
    return {
        "status": "ERROR",
        "error_code": "KAKAO_LOGIN_REQUIRED",
        "message_ko": "카카오 채널 관리자센터 로그인/2FA 후 다시 실행하세요.",
    }
