from __future__ import annotations

from typing import Protocol


class KakaoChannelPage(Protocol):
    def open_message_composer(self) -> None: ...

    def send_friend_message(self, recipient: str, part_index: int, text: str) -> None: ...


class KakaoChatPage(Protocol):
    def send_chat_reply(self, contact_id: str, text: str) -> None: ...
