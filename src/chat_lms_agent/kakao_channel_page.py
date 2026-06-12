from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

    from chat_lms_agent.kakao_calibration import KakaoCalibrationPack


class KakaoChannelPage(Protocol):
    def open_message_composer(self) -> None: ...

    def send_friend_message(self, recipient: str, part_index: int, text: str) -> None: ...


class KakaoChatPage(Protocol):
    def send_chat_reply(self, contact_id: str, text: str) -> None: ...


@dataclass(frozen=True, slots=True)
class PlaywrightKakaoChannelPage:
    page: Page
    calibration: KakaoCalibrationPack

    def open_message_composer(self) -> None:
        _click_first(self.page.locator(self.calibration.selectors["message_composer"]))

    def send_friend_message(self, recipient: str, part_index: int, text: str) -> None:
        _ = (recipient, part_index)
        _fill_first(self.page.locator(self.calibration.selectors["message_textarea"]), text)
        _click_first(self.page.locator(self.calibration.selectors["send_button"]))


@dataclass(frozen=True, slots=True)
class PlaywrightKakaoChatPage:
    page: Page
    calibration: KakaoCalibrationPack

    def send_chat_reply(self, contact_id: str, text: str) -> None:
        thread = self.page.locator(self.calibration.selectors["chat_thread"]).filter(
            has_text=contact_id,
        )
        _click_first(thread)
        _fill_first(self.page.locator(self.calibration.selectors["chat_reply_textarea"]), text)
        _click_first(self.page.locator(self.calibration.selectors["chat_reply_button"]))


def _click_first(locator: Locator) -> None:
    locator.filter(visible=True).first.click()


def _fill_first(locator: Locator, value: str) -> None:
    locator.filter(visible=True).first.fill(value)
