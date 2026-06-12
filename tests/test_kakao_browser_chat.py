from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from chat_lms_agent.kakao_browser_chat import (
    KakaoAuthenticatedChatClient,
    KakaoChatApiError,
    KakaoChatPullResult,
    KakaoPulledThread,
    profile_id_from_admin_url,
)
from chat_lms_agent.kakao_core import KakaoChatMessage, load_chat_history
from chat_lms_agent.kakao_handlers import handle_kakao
from chat_lms_agent.kakao_live_handlers import handle_kakao_chats_pull
from chat_lms_agent.state import ProfileState, resolve_profile_state

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture


@dataclass(frozen=True, slots=True)
class _FakeResponse:
    status: int
    payload: object
    body_bytes: bytes = b""

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> object:
        return self.payload

    def body(self) -> bytes:
        return self.body_bytes


@dataclass(slots=True)
class _FakeRequest:
    search_payload: dict[str, object]
    logs_payload: dict[str, object]
    status: int = 200
    posts: list[tuple[str, dict[str, str] | None, dict[str, str] | None]] = field(
        default_factory=list,
    )
    gets: list[str] = field(default_factory=list)

    def get(self, url: str) -> _FakeResponse:
        self.gets.append(url)
        if "media.example.test" in url:
            return _FakeResponse(200, {}, body_bytes=b"image-bytes")
        return _FakeResponse(self.status, self.logs_payload)

    def post(
        self,
        url: str,
        *,
        data: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        multipart: dict[str, str] | None = None,
    ) -> _FakeResponse:
        _ = headers
        self.posts.append((url, data, multipart))
        if url.endswith("/chatlogs"):
            return _FakeResponse(self.status, {"status": "ok"})
        return _FakeResponse(self.status, self.search_payload)


def test_profile_id_from_admin_url_reads_channel_segment() -> None:
    assert (
        profile_id_from_admin_url("https://business.kakao.com/_abc123/profile/settings")
        == "_abc123"
    )


def test_chat_client_pulls_threads_and_normalizes_log_messages() -> None:
    request = _FakeRequest(
        search_payload={
            "items": [
                {"chat_id": "chat-1", "name": "synthetic-contact"},
            ],
        },
        logs_payload={
            "items": [
                {
                    "id": "log-1",
                    "author_id": "user-1",
                    "profile_id": "_channel",
                    "message": "hello",
                    "send_at": 0,
                    "attachment": {"url": "https://media.example.test/photo.jpg"},
                },
                {
                    "id": "log-2",
                    "author_id": "_channel",
                    "profile_id": "_channel",
                    "message": "reply",
                    "send_at": 1000,
                },
            ],
        },
    )
    client = KakaoAuthenticatedChatClient(profile_id="_channel", request=request)

    result = client.pull_threads(download_media=True)

    assert len(result.threads) == 1
    thread = result.threads[0]
    assert thread.contact_id == "synthetic-contact"
    assert thread.chat_id == "chat-1"
    assert thread.messages == (
        KakaoChatMessage(
            message_id="log-1",
            direction="inbound",
            text="hello",
            sent_at="1970-01-01T00:00:00+00:00",
            media_urls=("https://media.example.test/photo.jpg",),
        ),
            KakaoChatMessage(
                message_id="log-2",
                direction="outbound",
                text="reply",
                sent_at="1970-01-01T00:16:40+00:00",
            ),
        )
    assert result.media_by_url == {"https://media.example.test/photo.jpg": b"image-bytes"}


def test_chat_client_sends_reply_to_resolved_chat() -> None:
    request = _FakeRequest(
        search_payload={"items": [{"chat_id": "chat-1", "name": "synthetic-contact"}]},
        logs_payload={"items": []},
    )
    client = KakaoAuthenticatedChatClient(profile_id="_channel", request=request)

    result = client.send_reply(contact_id="synthetic-contact", text="approved reply")

    assert result.contact_id == "synthetic-contact"
    assert result.chat_id == "chat-1"
    assert request.posts[-1] == (
        "https://business.kakao.com/api/profiles/_channel/chats/chat-1/chatlogs",
        None,
        {"text": "approved reply"},
    )


def test_chat_client_reports_login_required_on_unauthorized_search() -> None:
    client = KakaoAuthenticatedChatClient(
        profile_id="_channel",
        request=_FakeRequest(search_payload={}, logs_payload={}, status=401),
    )

    with pytest.raises(KakaoChatApiError, match="KAKAO_LOGIN_REQUIRED"):
        _ = client.pull_threads()


def test_chats_pull_handler_ingests_messages_and_media(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    media_url = "https://media.example.test/photo.jpg"

    def fake_pull(*, admin_url: str, headed: bool) -> KakaoChatPullResult:
        assert admin_url == "https://business.kakao.com/_channel/profile/settings"
        assert not headed
        return KakaoChatPullResult(
            threads=(
                KakaoPulledThread(
                    contact_id="synthetic-contact",
                    chat_id="chat-1",
                    messages=(
                        KakaoChatMessage(
                            message_id="log-1",
                            direction="inbound",
                            text="photo",
                            sent_at="2026-06-12T00:00:00+00:00",
                            media_urls=(media_url,),
                        ),
                    ),
                ),
            ),
            media_by_url={media_url: b"image-bytes"},
        )

    monkeypatch.setattr("chat_lms_agent.kakao_live_handlers.pull_kakao_chat_threads", fake_pull)

    code = handle_kakao_chats_pull(
        [
            "kakao",
            "chats",
            "pull",
            "--admin-url",
            "https://business.kakao.com/_channel/profile/settings",
            "--profile-root",
            str(tmp_path),
            "--json",
        ],
        _repo_root(),
    )

    payload = json.loads(capsys.readouterr().out)
    loaded = load_chat_history(profile, contact_id="synthetic-contact")
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["threads"][0]["new_count"] == 1
    assert loaded[0].media_refs == (
        "<profile-root>/.chat-lms-state/kakao/media/synthetic-contact/log-1/0.bin",
    )


def test_chats_reply_handler_requests_approval_before_live_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    def fail_send(*, admin_url: str, headed: bool, contact_id: str, text: str) -> object:
        _ = (admin_url, headed, contact_id, text)
        raise AssertionError

    monkeypatch.setattr("chat_lms_agent.kakao_live_handlers.send_kakao_chat_reply", fail_send)

    code = handle_kakao(
        [
            "kakao",
            "chats",
            "reply",
            "--contact",
            "synthetic-contact",
            "--message",
            "hello",
            "--profile-root",
            str(tmp_path),
            "--json",
        ],
        _repo_root(),
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 3
    assert payload["status"] == "NEEDS_APPROVAL"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
