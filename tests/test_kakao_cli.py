from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from chat_lms_agent.approvals import approve_request, show_approval
from chat_lms_agent.kakao_calibration import (
    CALIBRATION_SCHEMA_VERSION,
    REQUIRED_SELECTORS,
    calibration_pack_path,
)
from chat_lms_agent.kakao_core import KakaoChatMessage, ingest_chat_history
from chat_lms_agent.kakao_handlers import (
    KakaoFriendSendRequest,
    send_chat_reply,
    send_friend_with_page,
)
from chat_lms_agent.kakao_quota import record_kakao_send_usage, summarize_kakao_quota
from chat_lms_agent.kakao_summary import KakaoGeneratedSummary, store_generated_chat_summary
from chat_lms_agent.state import ProfileState, resolve_profile_state


@dataclass(slots=True)
class _RecordingReplyPage:
    replies: list[tuple[str, str]] = field(default_factory=list)
    fail: bool = False

    def send_chat_reply(self, contact_id: str, text: str) -> None:
        if self.fail:
            raise RuntimeError
        self.replies.append((contact_id, text))


@dataclass(slots=True)
class _RecordingFriendPage:
    sent: list[tuple[str, int, str]] = field(default_factory=list)
    fail_on_part_index: int | None = None

    def open_message_composer(self) -> None:
        return None

    def send_friend_message(self, recipient: str, part_index: int, text: str) -> None:
        if self.fail_on_part_index == part_index:
            raise RuntimeError
        self.sent.append((recipient, part_index, text))


def test_send_friend_demands_recipient_bound_approval_before_browser(tmp_path: Path) -> None:
    # Given: a friend-group broadcast with no approval id and no calibration.
    # When: the CLI command is run.
    result = _run_cli(
        "kakao",
        "send-friend",
        "--group",
        "parents",
        "--message",
        "June notice",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: approval is requested before any calibration/browser work.
    assert result.returncode == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "NEEDS_APPROVAL"
    assert "parents" in payload["operation"]
    assert "KAKAO_CALIBRATION_REQUIRED" not in result.stdout


def test_send_friend_with_approval_stops_at_missing_calibration_without_consuming(
    tmp_path: Path,
) -> None:
    # Given: an approved recipient-bound friend broadcast.
    first = _run_cli(
        "kakao",
        "send-friend",
        "--group",
        "parents",
        "--message",
        "June notice",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    approval_id = str(json.loads(first.stdout)["approval_id"])
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    code, _payload = approve_request(profile, approval_id, "teacher")
    assert code == 0

    # When: the approved command runs without a calibration pack.
    second = _run_cli(
        "kakao",
        "send-friend",
        "--group",
        "parents",
        "--message",
        "June notice",
        "--approval-id",
        approval_id,
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: it stops with a typed calibration error and leaves approval reusable.
    assert second.returncode == 2, second.stdout
    payload = json.loads(second.stdout)
    assert payload["error_code"] == "KAKAO_CALIBRATION_REQUIRED"
    show_code, approval = show_approval(profile, approval_id)
    assert show_code == 0
    assert approval["approval_status"] == "APPROVED"


def test_chat_reply_uses_single_use_approval(tmp_path: Path) -> None:
    # Given: the chat-reply handler is driven through its CLI approval path
    # with a fake page, so CI never touches KakaoTalk.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    first_page = _RecordingReplyPage()
    first = send_chat_reply(
        profile,
        contact_id="synthetic-contact",
        message="Synthetic reply",
        approval_id=None,
        page=first_page,
    )
    assert first.exit_code == 3
    assert first.payload["status"] == "NEEDS_APPROVAL"
    approval_id = str(first.payload["approval_id"])
    code, _payload = approve_request(profile, approval_id, "teacher")
    assert code == 0

    # When: the approved reply succeeds once and is retried with the same id.
    second_page = _RecordingReplyPage()
    second = send_chat_reply(
        profile,
        contact_id="synthetic-contact",
        message="Synthetic reply",
        approval_id=approval_id,
        page=second_page,
    )
    third = send_chat_reply(
        profile,
        contact_id="synthetic-contact",
        message="Synthetic reply",
        approval_id=approval_id,
        page=_RecordingReplyPage(),
    )

    # Then: the first success consumes approval and the retry is blocked.
    assert second.exit_code == 0
    assert second_page.replies == [("synthetic-contact", "Synthetic reply")]
    assert third.exit_code == 5
    assert third.payload["error_code"] == "KAKAO_APPROVAL_UNAVAILABLE"


def test_chat_reply_records_quota_only_after_page_success(tmp_path: Path) -> None:
    # Given: an approved chat reply with a successful fake page.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    first = send_chat_reply(
        profile,
        contact_id="synthetic-contact",
        message="Synthetic reply",
        approval_id=None,
        page=_RecordingReplyPage(),
    )
    approval_id = str(first.payload["approval_id"])
    code, _payload = approve_request(profile, approval_id, "teacher")
    assert code == 0

    # When: the approved reply succeeds through the page seam.
    result = send_chat_reply(
        profile,
        contact_id="synthetic-contact",
        message="Synthetic reply",
        approval_id=approval_id,
        page=_RecordingReplyPage(),
    )

    # Then: one quota unit is recorded.
    quota = summarize_kakao_quota(
        profile,
        free_quota_ceiling=10,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )
    assert result.exit_code == 0
    assert quota.month_to_date_sent == 1


def test_chat_reply_does_not_record_quota_when_page_fails(tmp_path: Path) -> None:
    # Given: an approved chat reply whose fake page fails.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    first = send_chat_reply(
        profile,
        contact_id="synthetic-contact",
        message="Synthetic reply",
        approval_id=None,
        page=_RecordingReplyPage(),
    )
    approval_id = str(first.payload["approval_id"])
    code, _payload = approve_request(profile, approval_id, "teacher")
    assert code == 0

    # When/Then: the page failure propagates and quota remains untouched.
    with pytest.raises(RuntimeError):
        _ = send_chat_reply(
            profile,
            contact_id="synthetic-contact",
            message="Synthetic reply",
            approval_id=approval_id,
            page=_RecordingReplyPage(fail=True),
        )
    quota = summarize_kakao_quota(
        profile,
        free_quota_ceiling=10,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )
    assert quota.month_to_date_sent == 0


def test_friend_broadcast_records_only_newly_sent_quota_parts(tmp_path: Path) -> None:
    # Given: a two-part approved friend broadcast with the first part checkpointed.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    first = send_friend_with_page(
        profile,
        request=KakaoFriendSendRequest(
            recipient="friend-group:parents",
            message=("a" * 400) + ("b" * 50),
            approval_id=None,
            checkpoint=tmp_path / "friend.checkpoint.json",
        ),
        page=_RecordingFriendPage(),
    )
    approval_id = str(first.payload["approval_id"])
    code, _payload = approve_request(profile, approval_id, "teacher")
    assert code == 0
    checkpoint = tmp_path / "friend.checkpoint.json"
    checkpoint.write_text(json.dumps({"completed_part_indexes": [0]}), encoding="utf-8")

    # When: the approved broadcast resumes and sends only the missing part.
    result = send_friend_with_page(
        profile,
        request=KakaoFriendSendRequest(
            recipient="friend-group:parents",
            message=("a" * 400) + ("b" * 50),
            approval_id=approval_id,
            checkpoint=checkpoint,
        ),
        page=_RecordingFriendPage(),
    )

    # Then: quota records one newly sent part, not both checkpointed parts.
    quota = summarize_kakao_quota(
        profile,
        free_quota_ceiling=10,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )
    assert result.exit_code == 0
    assert result.payload["completed_parts"] == 2
    assert quota.month_to_date_sent == 1


def test_friend_broadcast_records_no_quota_for_already_complete_checkpoint(
    tmp_path: Path,
) -> None:
    # Given: an approved broadcast whose checkpoint is already complete.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    first = send_friend_with_page(
        profile,
        request=KakaoFriendSendRequest(
            recipient="friend-group:parents",
            message=("a" * 400) + ("b" * 50),
            approval_id=None,
            checkpoint=tmp_path / "friend.checkpoint.json",
        ),
        page=_RecordingFriendPage(),
    )
    approval_id = str(first.payload["approval_id"])
    code, _payload = approve_request(profile, approval_id, "teacher")
    assert code == 0
    checkpoint = tmp_path / "friend.checkpoint.json"
    checkpoint.write_text(json.dumps({"completed_part_indexes": [0, 1]}), encoding="utf-8")

    # When: the approved broadcast is retried.
    result = send_friend_with_page(
        profile,
        request=KakaoFriendSendRequest(
            recipient="friend-group:parents",
            message=("a" * 400) + ("b" * 50),
            approval_id=approval_id,
            checkpoint=checkpoint,
        ),
        page=_RecordingFriendPage(),
    )

    # Then: success is idempotent and quota remains zero.
    quota = summarize_kakao_quota(
        profile,
        free_quota_ceiling=10,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )
    assert result.exit_code == 0
    assert result.payload["completed_parts"] == 2
    assert quota.month_to_date_sent == 0


def test_friend_broadcast_does_not_record_quota_on_send_failure(tmp_path: Path) -> None:
    # Given: an approved two-part broadcast whose missing part fails.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    first = send_friend_with_page(
        profile,
        request=KakaoFriendSendRequest(
            recipient="friend-group:parents",
            message=("a" * 400) + ("b" * 50),
            approval_id=None,
            checkpoint=tmp_path / "friend.checkpoint.json",
        ),
        page=_RecordingFriendPage(),
    )
    approval_id = str(first.payload["approval_id"])
    code, _payload = approve_request(profile, approval_id, "teacher")
    assert code == 0
    checkpoint = tmp_path / "friend.checkpoint.json"
    checkpoint.write_text(json.dumps({"completed_part_indexes": [0]}), encoding="utf-8")

    # When: the page seam fails on the missing part.
    result = send_friend_with_page(
        profile,
        request=KakaoFriendSendRequest(
            recipient="friend-group:parents",
            message=("a" * 400) + ("b" * 50),
            approval_id=approval_id,
            checkpoint=checkpoint,
        ),
        page=_RecordingFriendPage(fail_on_part_index=1),
    )

    # Then: failure is reported and no quota is recorded.
    quota = summarize_kakao_quota(
        profile,
        free_quota_ceiling=10,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )
    assert result.exit_code == 1
    assert result.payload["error_code"] == "KAKAO_SEND_FAILED"
    assert quota.month_to_date_sent == 0


def test_calibrate_redacts_profile_local_calibration_path(tmp_path: Path) -> None:
    # Given: a profile-local workspace path that must not leak through JSON output.
    # When: calibration guidance is requested from the CLI.
    result = _run_cli(
        "kakao",
        "calibrate",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the output uses the public placeholder path.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "KAKAO_CALIBRATION_REQUIRED"
    assert payload["calibration_pack"] == "<profile-root>/.chat-lms-state/kakao/calibration.json"
    assert str(tmp_path) not in result.stdout


def test_chats_pull_requires_login_after_valid_calibration(tmp_path: Path) -> None:
    # Given: a syntactically valid profile-local calibration pack.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    _write_calibration_pack(profile)

    # When: chat pull is requested without a live Kakao browser session.
    result = _run_cli(
        "kakao",
        "chats",
        "pull",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: calibration has passed, so the typed stop is login/session-related.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "KAKAO_LOGIN_REQUIRED"
    assert "KAKAO_CALIBRATION_REQUIRED" not in result.stdout


def test_summary_cli_returns_generated_summary_fields(tmp_path: Path) -> None:
    # Given: stored synthetic chat history and a host/model generated summary.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    _ = ingest_chat_history(
        profile,
        contact_id="synthetic-contact",
        messages=(
            KakaoChatMessage(
                message_id="m1",
                direction="inbound",
                text="Synthetic parent asks for homework.",
                sent_at="2026-06-12T09:00:00+09:00",
            ),
        ),
    )
    store_generated_chat_summary(
        profile,
        summary=KakaoGeneratedSummary(
            contact_id="synthetic-contact",
            summary_text="Parent asked for homework; teacher should send worksheet.",
            generated_at="2026-06-12T09:01:00+09:00",
            model_id="host-model:test",
            through_message_id="m1",
        ),
    )

    # When: the summary CLI is called.
    result = _run_cli(
        "kakao",
        "summary",
        "--contact",
        "synthetic-contact",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: generated summary fields are visible and private paths are absent.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["summary_text"] == "Parent asked for homework; teacher should send worksheet."
    assert payload["summary_source"] == "generated"
    assert payload["summary_model_id"] == "host-model:test"
    assert str(tmp_path) not in result.stdout


def test_status_reports_quota_usage_from_profile_ledger(tmp_path: Path) -> None:
    # Given: calibration includes a free quota ceiling and profile usage is recorded.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    _write_calibration_pack(profile, free_quota_ceiling=3)
    record_kakao_send_usage(
        profile,
        sent_at="2026-06-12T09:00:00+09:00",
        units=3,
        surface="friend_broadcast",
        recipient="friend-group:parents",
    )

    # When: Kakao status is requested.
    result = _run_cli(
        "kakao",
        "status",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the status payload reports month-to-date quota state.
    assert result.returncode == 0, result.stdout
    kakao = json.loads(result.stdout)["kakao"]
    assert kakao["month_to_date_sent"] == 3
    assert kakao["free_quota_ceiling"] == 3
    assert kakao["quota_remaining"] == 0
    assert kakao["quota_state"] == "warning"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_calibration_pack(profile: ProfileState, *, free_quota_ceiling: int = 1000) -> None:
    pack_path = calibration_pack_path(profile)
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(
        json.dumps(
            {
                "schema_version": CALIBRATION_SCHEMA_VERSION,
                "captured_at": "2026-06-11T00:00:00Z",
                "free_quota_ceiling": free_quota_ceiling,
                "selectors": {key: f"synthetic-selector-{key}" for key in REQUIRED_SELECTORS},
            },
        ),
        encoding="utf-8",
    )


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    env["CHAT_LMS_AGENT_KAKAO_NOW"] = "2026-06-12T00:00:00+09:00"
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
        input="",
    )
