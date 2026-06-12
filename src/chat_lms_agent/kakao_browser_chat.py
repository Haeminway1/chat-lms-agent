from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, cast, override
from urllib.parse import urlparse

from chat_lms_agent.kakao_core import KakaoChatMessage

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chat_lms_agent.state import JsonValue

EPOCH_MS_THRESHOLD = 10_000_000_000


@dataclass(frozen=True, slots=True)
class KakaoChatApiError(RuntimeError):
    error_code: str
    message: str

    @override
    def __str__(self) -> str:
        return f"{self.error_code}: {self.message}"


@dataclass(frozen=True, slots=True)
class KakaoPulledThread:
    contact_id: str
    chat_id: str
    messages: tuple[KakaoChatMessage, ...]


@dataclass(frozen=True, slots=True)
class KakaoChatPullResult:
    threads: tuple[KakaoPulledThread, ...]
    media_by_url: Mapping[str, bytes]


@dataclass(frozen=True, slots=True)
class KakaoChatReplyResult:
    contact_id: str
    chat_id: str


class KakaoHttpResponse(Protocol):
    @property
    def ok(self) -> bool: ...

    @property
    def status(self) -> int: ...

    def json(self) -> object: ...

    def body(self) -> bytes: ...


class KakaoHttpRequest(Protocol):
    def get(self, url: str) -> KakaoHttpResponse: ...

    def post(
        self,
        url: str,
        *,
        data: object | None = None,
        headers: dict[str, str] | None = None,
        multipart: dict[str, str] | None = None,
    ) -> KakaoHttpResponse: ...


@dataclass(frozen=True, slots=True)
class _ChatRecord:
    contact_id: str
    chat_id: str


@dataclass(frozen=True, slots=True)
class KakaoAuthenticatedChatClient:
    profile_id: str
    request: KakaoHttpRequest
    api_root: str = "https://business.kakao.com/api"

    def pull_threads(
        self,
        *,
        contact_id: str | None = None,
        download_media: bool = False,
    ) -> KakaoChatPullResult:
        threads: list[KakaoPulledThread] = []
        media_by_url: dict[str, bytes] = {}
        for chat in self._list_chats():
            if contact_id is not None and contact_id not in {chat.contact_id, chat.chat_id}:
                continue
            messages = self._chatlogs(chat.chat_id)
            if download_media:
                self._fetch_media(messages, media_by_url)
            threads.append(
                KakaoPulledThread(
                    contact_id=chat.contact_id,
                    chat_id=chat.chat_id,
                    messages=messages,
                ),
            )
        return KakaoChatPullResult(threads=tuple(threads), media_by_url=media_by_url)

    def send_reply(self, *, contact_id: str, text: str) -> KakaoChatReplyResult:
        chat = self._resolve_chat(contact_id)
        response = self.request.post(
            self._chatlogs_url(chat.chat_id),
            multipart={"text": text},
        )
        _ = _json_mapping(response, endpoint="chat reply")
        return KakaoChatReplyResult(contact_id=chat.contact_id, chat_id=chat.chat_id)

    def _resolve_chat(self, contact_id: str) -> _ChatRecord:
        for chat in self._list_chats():
            if contact_id in {chat.contact_id, chat.chat_id}:
                return chat
        raise KakaoChatApiError(
            error_code="KAKAO_CHAT_NOT_FOUND",
            message="Kakao chat contact was not found in the channel chat list.",
        )

    def _list_chats(self) -> tuple[_ChatRecord, ...]:
        response = self.request.post(
            f"{self.api_root}/profiles/{self.profile_id}/chats/search?size=100",
            data={},
        )
        payload = _json_mapping(response, endpoint="chat search")
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            return ()
        chats: list[_ChatRecord] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            parsed = _chat_record_from_json(raw_item)
            if parsed is not None:
                chats.append(parsed)
        return tuple(chats)

    def _chatlogs(self, chat_id: str) -> tuple[KakaoChatMessage, ...]:
        response = self.request.get(f"{self._chatlogs_url(chat_id)}?size=100")
        payload = _json_mapping(response, endpoint="chat logs")
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            return ()
        messages: list[KakaoChatMessage] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            parsed = _message_from_json(raw_item, profile_id=self.profile_id)
            if parsed is not None:
                messages.append(parsed)
        return tuple(messages)

    def _fetch_media(
        self,
        messages: tuple[KakaoChatMessage, ...],
        media_by_url: dict[str, bytes],
    ) -> None:
        for message in messages:
            if message.direction != "inbound":
                continue
            for url in message.media_urls:
                if url not in media_by_url:
                    media_by_url[url] = self.request.get(url).body()

    def _chatlogs_url(self, chat_id: str) -> str:
        return f"{self.api_root}/profiles/{self.profile_id}/chats/{chat_id}/chatlogs"


def profile_id_from_admin_url(admin_url: str) -> str:
    parsed = urlparse(admin_url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        raise KakaoChatApiError(
            error_code="KAKAO_PROFILE_ID_MISSING",
            message="Kakao admin URL does not include a channel profile id.",
        )
    return segments[0]


def _json_mapping(response: KakaoHttpResponse, *, endpoint: str) -> dict[str, JsonValue]:
    if not response.ok:
        if response.status in {401, 403}:
            raise KakaoChatApiError(
                error_code="KAKAO_LOGIN_REQUIRED",
                message=f"Kakao {endpoint} request requires a valid login session.",
            )
        raise KakaoChatApiError(
            error_code="KAKAO_CHAT_API_FAILED",
            message=f"Kakao {endpoint} request failed with HTTP {response.status}.",
        )
    payload = cast("JsonValue", response.json())
    if isinstance(payload, dict):
        return payload
    raise KakaoChatApiError(
        error_code="KAKAO_CHAT_API_INVALID",
        message=f"Kakao {endpoint} response was not a JSON object.",
    )


def _chat_record_from_json(payload: dict[str, JsonValue]) -> _ChatRecord | None:
    chat_id = _string_value(payload.get("chat_id")) or _string_value(payload.get("id"))
    contact_id = (
        _string_value(payload.get("name"))
        or _string_value(payload.get("nickname"))
        or _string_value(payload.get("display_name"))
        or chat_id
    )
    if chat_id is None or contact_id is None:
        return None
    return _ChatRecord(contact_id=contact_id, chat_id=chat_id)


def _message_from_json(
    payload: dict[str, JsonValue],
    *,
    profile_id: str,
) -> KakaoChatMessage | None:
    message_id = _string_value(payload.get("id")) or _string_value(payload.get("log_id"))
    if message_id is None:
        return None
    text = payload.get("message")
    author_id = _string_value(payload.get("author_id"))
    return KakaoChatMessage(
        message_id=message_id,
        direction="outbound" if author_id == profile_id else "inbound",
        text=text if isinstance(text, str) else "",
        sent_at=_sent_at_to_iso(payload.get("send_at")),
        media_urls=_media_urls(payload.get("attachment")),
    )


def _sent_at_to_iso(value: object) -> str:
    if isinstance(value, bool):
        return ""
    if isinstance(value, int | float):
        seconds = value / 1000 if value > EPOCH_MS_THRESHOLD else value
        return datetime.fromtimestamp(seconds, UTC).isoformat()
    return value if isinstance(value, str) else ""


def _media_urls(value: object) -> tuple[str, ...]:
    found: list[str] = []
    _collect_urls(value, found)
    return tuple(dict.fromkeys(found))


def _collect_urls(value: object, found: list[str]) -> None:
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            found.append(value)
        return
    if isinstance(value, list):
        for item in cast("list[object]", value):
            _collect_urls(item, found)
        return
    if isinstance(value, dict):
        for item in cast("dict[object, object]", value).values():
            _collect_urls(item, found)


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return None
