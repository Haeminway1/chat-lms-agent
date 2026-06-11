from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from chat_lms_agent.approvals import approve_request, show_approval
from chat_lms_agent.kakao_calibration import (
    CALIBRATION_SCHEMA_VERSION,
    REQUIRED_SELECTORS,
    calibration_pack_path,
)
from chat_lms_agent.kakao_handlers import send_chat_reply
from chat_lms_agent.state import ProfileState, resolve_profile_state


@dataclass(slots=True)
class _RecordingReplyPage:
    replies: list[tuple[str, str]] = field(default_factory=list)

    def send_chat_reply(self, contact_id: str, text: str) -> None:
        self.replies.append((contact_id, text))


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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _write_calibration_pack(profile: ProfileState) -> None:
    pack_path = calibration_pack_path(profile)
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(
        json.dumps(
            {
                "schema_version": CALIBRATION_SCHEMA_VERSION,
                "captured_at": "2026-06-11T00:00:00Z",
                "free_quota_ceiling": 1000,
                "selectors": {key: f"synthetic-selector-{key}" for key in REQUIRED_SELECTORS},
            },
        ),
        encoding="utf-8",
    )


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
        input="",
    )
