from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent.kakao_live_handlers import handle_kakao_login
from chat_lms_agent.kakao_login import KakaoBrowserOptions, KakaoLoginResult, run_kakao_login

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    import pytest
    from _pytest.capture import CaptureFixture


@dataclass(slots=True)
class _FakePage:
    url: str = "https://business.kakao.com/_test/profile/settings"
    redirect_to_login: bool = False
    actions: list[tuple[str, str]] = field(default_factory=list)

    def set_default_timeout(self, timeout: int) -> None:
        self.actions.append(("timeout", str(timeout)))

    def goto(self, url: str, *, wait_until: str) -> None:
        self.actions.append(("goto", url))
        self.url = "https://accounts.kakao.com/login" if self.redirect_to_login else url
        _ = wait_until

    def wait_for_url(
        self,
        matcher: Callable[[str], bool],
        *,
        timeout: int,
        wait_until: str,
    ) -> None:
        self.actions.append(("wait_for_url", str(timeout)))
        self.url = "https://business.kakao.com/_test/chats"
        assert matcher(self.url)
        _ = wait_until

    def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        self.actions.append(("wait_for_load_state", state))
        _ = timeout


@dataclass(slots=True)
class _FakeContext:
    page: _FakePage
    closed: bool = False

    @property
    def pages(self) -> list[_FakePage]:
        return [self.page]

    def new_page(self) -> _FakePage:
        return self.page

    def close(self) -> None:
        self.closed = True


@dataclass(slots=True)
class _FakeChromium:
    context: _FakeContext
    launch_args: list[tuple[str, bool, int]] = field(default_factory=list)

    def launch_persistent_context(
        self,
        profile_dir: str,
        *,
        headless: bool,
        slow_mo: int,
    ) -> _FakeContext:
        self.launch_args.append((profile_dir, headless, slow_mo))
        return self.context


@dataclass(slots=True)
class _FakeRuntime:
    chromium: _FakeChromium


@dataclass(slots=True)
class _FakeManager:
    runtime: _FakeRuntime

    def __enter__(self) -> _FakeRuntime:
        return self.runtime

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        _ = (exc_type, exc, traceback)
        return False


def test_run_kakao_login_opens_persistent_profile_with_selected_start_url(
    tmp_path: Path,
) -> None:
    page = _FakePage(redirect_to_login=True)
    context = _FakeContext(page)
    chromium = _FakeChromium(context)
    runtime = _FakeRuntime(chromium)

    result = run_kakao_login(
        KakaoBrowserOptions(
            profile_dir=tmp_path / "kakao-profile",
            headed=True,
            slow_mo_ms=25,
            start_url="https://business.kakao.com/_test/profile/settings",
        ),
        playwright_factory=lambda: _FakeManager(runtime),
    )

    assert result == KakaoLoginResult(
        status="logged_in",
        profile_dir=tmp_path / "kakao-profile",
        current_url="https://business.kakao.com/_test/chats",
    )
    assert chromium.launch_args == [(str(tmp_path / "kakao-profile"), False, 25)]
    assert ("goto", "https://business.kakao.com/_test/profile/settings") in page.actions
    assert context.closed


def test_login_handler_uses_calibrated_admin_url_without_leaking_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    captured: list[KakaoBrowserOptions] = []

    def fake_login(options: KakaoBrowserOptions) -> KakaoLoginResult:
        captured.append(options)
        return KakaoLoginResult(
            status="logged_in",
            profile_dir=Path.home() / ".chat_lms_agent" / "kakao-channel-profile",
            current_url="https://business.kakao.com/_test/profile/settings",
        )

    _write_calibration_pack(tmp_path)
    monkeypatch.setattr("chat_lms_agent.kakao_live_handlers.run_kakao_login", fake_login)

    code = handle_kakao_login(
        ["kakao", "login", "--headed", "--profile-root", str(tmp_path), "--json"],
        _repo_root(),
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["profile_dir"] == "~/.chat_lms_agent/kakao-channel-profile"
    assert str(Path.home()) not in json.dumps(payload)
    assert captured[0].headed
    assert captured[0].start_url == "https://business.kakao.com/_test/profile/settings"


def test_login_handler_allows_live_admin_url_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    captured: list[KakaoBrowserOptions] = []

    def fake_login(options: KakaoBrowserOptions) -> KakaoLoginResult:
        captured.append(options)
        return KakaoLoginResult(
            status="logged_in",
            profile_dir=Path.home() / ".chat_lms_agent" / "kakao-channel-profile",
            current_url="https://business.kakao.com/_override/profile/settings",
        )

    monkeypatch.setattr("chat_lms_agent.kakao_live_handlers.run_kakao_login", fake_login)

    code = handle_kakao_login(
        [
            "kakao",
            "login",
            "--headed",
            "--admin-url",
            "https://business.kakao.com/_override/profile/settings",
            "--profile-root",
            str(tmp_path),
            "--json",
        ],
        _repo_root(),
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert captured[0].start_url == "https://business.kakao.com/_override/profile/settings"


def _write_calibration_pack(profile_root: Path) -> None:
    pack_path = profile_root / ".chat-lms-state" / "kakao" / "calibration.json"
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(
        json.dumps(
            {
                "schema_version": "kakao-calibration-v1",
                "captured_at": "2026-06-12T14:00:00+09:00",
                "admin_url": "https://business.kakao.com/_test/profile/settings",
                "selectors": {
                    "message_composer": "[data-test='message_composer']",
                    "message_textarea": "[data-test='message_textarea']",
                    "send_button": "[data-test='send_button']",
                    "chat_list": "[data-test='chat_list']",
                    "chat_thread": "[data-test='chat_thread']",
                    "chat_reply_textarea": "[data-test='chat_reply_textarea']",
                    "chat_reply_button": "[data-test='chat_reply_button']",
                },
            },
        ),
        encoding="utf-8",
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
