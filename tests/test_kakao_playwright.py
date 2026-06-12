from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Self

from chat_lms_agent.kakao_calibration import (
    CALIBRATION_SCHEMA_VERSION,
    REQUIRED_SELECTORS,
    KakaoCalibrationError,
    KakaoCalibrationPack,
    calibration_pack_path,
    load_calibration_pack,
)
from chat_lms_agent.kakao_channel_page import (
    PlaywrightKakaoChannelPage,
    PlaywrightKakaoChatPage,
)
from chat_lms_agent.state import ProfileState, resolve_profile_state

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


@dataclass(slots=True)
class _FakeLocator:
    page: _FakePage
    selector: str
    has_text: str | None = None

    @property
    def first(self) -> Self:
        return self

    def filter(self, *, has_text: str | None = None, visible: bool | None = None) -> Self:
        if has_text is not None:
            self.has_text = has_text
        if visible is not None:
            self.page.actions.append(("filter_visible", self.selector, str(visible)))
        return self

    def click(self) -> None:
        self.page.actions.append(("click", self.selector, self.has_text or ""))

    def fill(self, value: str) -> None:
        self.page.actions.append(("fill", self.selector, value))


@dataclass(slots=True)
class _FakePage:
    actions: list[tuple[str, str, str]] = field(default_factory=list)

    def locator(self, selector: str) -> _FakeLocator:
        self.actions.append(("locator", selector, ""))
        return _FakeLocator(self, selector)


def test_calibration_pack_preserves_profile_local_admin_url(tmp_path: Path) -> None:
    # Given: a calibration pack captured from a real channel URL.
    profile = _profile(tmp_path)
    pack_path = calibration_pack_path(profile)
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(
        json.dumps(
            {
                "schema_version": CALIBRATION_SCHEMA_VERSION,
                "captured_at": "2026-06-12T14:00:00+09:00",
                "admin_url": "https://business.kakao.com/_test/profile/settings",
                "free_quota_ceiling": 1000,
                "selectors": _selectors(),
            },
        ),
        encoding="utf-8",
    )

    # When: the pack is loaded.
    pack = load_calibration_pack(profile)

    # Then: the live URL is available to the browser adapter and never stored in source.
    assert not isinstance(pack, KakaoCalibrationError)
    assert pack.admin_url == "https://business.kakao.com/_test/profile/settings"


def test_channel_page_uses_only_calibrated_selectors_for_broadcast(tmp_path: Path) -> None:
    # Given: a loaded calibration pack with synthetic selector strings.
    pack = _loaded_pack(tmp_path)
    page = _FakePage()
    adapter = PlaywrightKakaoChannelPage(page, pack)

    # When: the broadcast actions run through the adapter.
    adapter.open_message_composer()
    adapter.send_friend_message("channel-friends", 0, "hello")

    # Then: every DOM action uses selectors from the calibration pack.
    action_selectors = [selector for _, selector, _ in page.actions if selector]
    for selector in action_selectors:
        assert selector in set(pack.selectors.values())
    assert ("fill", pack.selectors["message_textarea"], "hello") in page.actions
    assert ("click", pack.selectors["send_button"], "") in page.actions


def test_chat_page_uses_calibrated_thread_selector_and_contact_text(tmp_path: Path) -> None:
    # Given: a loaded calibration pack with a chat-thread selector.
    pack = _loaded_pack(tmp_path)
    page = _FakePage()
    adapter = PlaywrightKakaoChatPage(page, pack)

    # When: a reply is sent to one visible chat contact.
    adapter.send_chat_reply("synthetic-contact", "reply")

    # Then: contact matching is data-driven and compose controls come from the pack.
    assert ("click", pack.selectors["chat_thread"], "synthetic-contact") in page.actions
    assert ("fill", pack.selectors["chat_reply_textarea"], "reply") in page.actions
    assert ("click", pack.selectors["chat_reply_button"], "") in page.actions


def _loaded_pack(tmp_path: Path) -> KakaoCalibrationPack:
    profile = _profile(tmp_path)
    pack_path = calibration_pack_path(profile)
    pack_path.parent.mkdir(parents=True, exist_ok=True)
    pack_path.write_text(
        json.dumps(
            {
                "schema_version": CALIBRATION_SCHEMA_VERSION,
                "captured_at": "2026-06-12T14:00:00+09:00",
                "admin_url": "https://business.kakao.com/_test/profile/settings",
                "free_quota_ceiling": 1000,
                "selectors": _selectors(),
            },
        ),
        encoding="utf-8",
    )
    pack = load_calibration_pack(profile)
    assert not isinstance(pack, KakaoCalibrationError)
    return pack


def _selectors() -> dict[str, JsonValue]:
    return {key: f"[data-chat-lms='{key}']" for key in REQUIRED_SELECTORS}


def _profile(tmp_path: Path) -> ProfileState:
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    return profile


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
