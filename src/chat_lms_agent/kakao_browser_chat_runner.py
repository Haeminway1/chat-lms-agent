from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from chat_lms_agent.kakao_browser_chat import (
    KakaoAuthenticatedChatClient,
    KakaoChatPullResult,
    KakaoChatReplyResult,
    KakaoHttpRequest,
    profile_id_from_admin_url,
)
from chat_lms_agent.kakao_login import (
    DEFAULT_TIMEOUT_MS,
    KAKAO_ADMIN_HOME,
    REDIRECT_SETTLE_MS,
    KakaoLoginRequiredError,
    KakaoPlaywrightMissingError,
    default_kakao_profile_dir,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from playwright.sync_api import Page


@dataclass(frozen=True, slots=True)
class KakaoBrowserChatOptions:
    admin_url: str
    profile_dir: Path | None = None
    headed: bool = False
    slow_mo_ms: int = 0


def pull_kakao_chat_threads(*, admin_url: str, headed: bool) -> KakaoChatPullResult:
    return _run_with_chat_client(
        KakaoBrowserChatOptions(admin_url=admin_url, headed=headed),
        lambda client: client.pull_threads(download_media=True),
    )


def send_kakao_chat_reply(
    *,
    admin_url: str,
    headed: bool,
    contact_id: str,
    text: str,
) -> KakaoChatReplyResult:
    return _run_with_chat_client(
        KakaoBrowserChatOptions(admin_url=admin_url, headed=headed),
        lambda client: client.send_reply(contact_id=contact_id, text=text),
    )


def _run_with_chat_client[T](
    options: KakaoBrowserChatOptions,
    action: Callable[[KakaoAuthenticatedChatClient], T],
) -> T:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise KakaoPlaywrightMissingError from exc

    profile_dir = options.profile_dir or default_kakao_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile_id = profile_id_from_admin_url(options.admin_url)
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            headless=not options.headed,
            slow_mo=options.slow_mo_ms,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            _prepare_page(page, options.admin_url, PlaywrightTimeoutError)
            request = cast("KakaoHttpRequest", cast("object", page.request))
            client = KakaoAuthenticatedChatClient(profile_id=profile_id, request=request)
            return action(client)
        finally:
            context.close()


def _prepare_page(
    page: Page,
    admin_url: str,
    timeout_error: type[Exception],
) -> None:
    page.set_default_timeout(DEFAULT_TIMEOUT_MS)
    _ = page.goto(admin_url or KAKAO_ADMIN_HOME, wait_until="domcontentloaded")
    with suppress(timeout_error):
        page.wait_for_load_state("networkidle", timeout=REDIRECT_SETTLE_MS)
    if "accounts.kakao.com" in page.url:
        raise KakaoLoginRequiredError
