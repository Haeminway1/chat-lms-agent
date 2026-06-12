from __future__ import annotations

from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal, Protocol

if TYPE_CHECKING:
    from contextlib import AbstractContextManager
    from types import TracebackType

    from playwright.sync_api import BrowserContext, BrowserType, Page, Playwright

KAKAO_ADMIN_HOME: Final = "https://business.kakao.com/"
KAKAO_PROFILE_DIR_NAME: Final = "kakao-channel-profile"
KAKAO_PROFILE_DISPLAY: Final = "~/.chat_lms_agent/kakao-channel-profile"
LOGIN_WAIT_MS: Final = 300_000
DEFAULT_TIMEOUT_MS: Final = 10_000

KakaoLoginStatus = Literal["logged_in"]
PageWaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]
PageLoadState = Literal["domcontentloaded", "load", "networkidle"]
DOMCONTENTLOADED: Final[PageWaitUntil] = "domcontentloaded"
NETWORKIDLE: Final[PageLoadState] = "networkidle"
REDIRECT_SETTLE_MS: Final = 15_000


class KakaoLoginError(RuntimeError):
    pass


class KakaoLoginRequiredError(KakaoLoginError):
    pass


class KakaoPlaywrightMissingError(KakaoLoginError):
    pass


@dataclass(frozen=True, slots=True)
class KakaoBrowserOptions:
    profile_dir: Path | None = None
    headed: bool = False
    slow_mo_ms: int = 0
    start_url: str | None = None


@dataclass(frozen=True, slots=True)
class KakaoLoginResult:
    status: KakaoLoginStatus
    profile_dir: Path
    current_url: str


class _Page(Protocol):
    @property
    def url(self) -> str: ...

    def set_default_timeout(self, timeout: int) -> None: ...

    def goto(self, url: str, *, wait_until: PageWaitUntil) -> None: ...

    def wait_for_url(
        self,
        matcher: Callable[[str], bool],
        *,
        timeout: int,
        wait_until: PageWaitUntil,
    ) -> None: ...

    def wait_for_load_state(self, state: PageLoadState, *, timeout: int) -> None: ...


class _Context(Protocol):
    @property
    def pages(self) -> list[_Page]: ...

    def new_page(self) -> _Page: ...

    def close(self) -> None: ...


class _Chromium(Protocol):
    def launch_persistent_context(
        self,
        profile_dir: str,
        *,
        headless: bool,
        slow_mo: int,
    ) -> _Context: ...


class _PlaywrightRuntime(Protocol):
    @property
    def chromium(self) -> _Chromium: ...


class _PlaywrightManager(Protocol):
    def __enter__(self) -> _PlaywrightRuntime: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...


type PlaywrightFactory = Callable[[], _PlaywrightManager]


@dataclass(frozen=True, slots=True)
class _PlaywrightRuntimeAdapter:
    runtime: Playwright

    @property
    def chromium(self) -> _Chromium:
        return _ChromiumAdapter(self.runtime.chromium)


@dataclass(frozen=True, slots=True)
class _ChromiumAdapter:
    browser_type: BrowserType

    def launch_persistent_context(
        self,
        profile_dir: str,
        *,
        headless: bool,
        slow_mo: int,
    ) -> _Context:
        context = self.browser_type.launch_persistent_context(
            profile_dir,
            headless=headless,
            slow_mo=slow_mo,
        )
        return _ContextAdapter(context)


@dataclass(frozen=True, slots=True)
class _ContextAdapter:
    context: BrowserContext

    @property
    def pages(self) -> list[_Page]:
        pages: list[_Page] = []
        pages.extend(_PageAdapter(page) for page in self.context.pages)
        return pages

    def new_page(self) -> _Page:
        return _PageAdapter(self.context.new_page())

    def close(self) -> None:
        self.context.close()


@dataclass(frozen=True, slots=True)
class _PageAdapter:
    page: Page

    @property
    def url(self) -> str:
        return self.page.url

    def set_default_timeout(self, timeout: int) -> None:
        self.page.set_default_timeout(timeout)

    def goto(self, url: str, *, wait_until: PageWaitUntil) -> None:
        _ = self.page.goto(url, wait_until=wait_until)

    def wait_for_url(
        self,
        matcher: Callable[[str], bool],
        *,
        timeout: int,
        wait_until: PageWaitUntil,
    ) -> None:
        self.page.wait_for_url(matcher, timeout=timeout, wait_until=wait_until)

    def wait_for_load_state(self, state: PageLoadState, *, timeout: int) -> None:
        self.page.wait_for_load_state(state, timeout=timeout)


@dataclass(frozen=True, slots=True)
class _PlaywrightManagerAdapter:
    manager: AbstractContextManager[Playwright]

    def __enter__(self) -> _PlaywrightRuntime:
        return _PlaywrightRuntimeAdapter(self.manager.__enter__())

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        return self.manager.__exit__(exc_type, exc, traceback)


def default_kakao_profile_dir() -> Path:
    return Path.home() / ".chat_lms_agent" / KAKAO_PROFILE_DIR_NAME


def run_kakao_login(
    options: KakaoBrowserOptions,
    *,
    playwright_factory: PlaywrightFactory | None = None,
) -> KakaoLoginResult:
    factory, timeout_error = _resolve_playwright(playwright_factory)
    profile_dir = options.profile_dir or default_kakao_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)
    with factory() as runtime:
        context = runtime.chromium.launch_persistent_context(
            str(profile_dir),
            headless=not options.headed,
            slow_mo=options.slow_mo_ms,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(DEFAULT_TIMEOUT_MS)
            page.goto(options.start_url or KAKAO_ADMIN_HOME, wait_until=DOMCONTENTLOADED)
            with suppress(timeout_error):
                page.wait_for_load_state(NETWORKIDLE, timeout=REDIRECT_SETTLE_MS)
            if _is_login_url(page.url):
                try:
                    page.wait_for_url(
                        lambda url: not _is_login_url(url),
                        timeout=LOGIN_WAIT_MS,
                        wait_until=DOMCONTENTLOADED,
                    )
                except timeout_error as exc:
                    raise KakaoLoginRequiredError from exc
            return KakaoLoginResult(
                status="logged_in",
                profile_dir=profile_dir,
                current_url=page.url,
            )
        finally:
            context.close()


def _resolve_playwright(
    playwright_factory: PlaywrightFactory | None,
) -> tuple[PlaywrightFactory, type[Exception]]:
    if playwright_factory is not None:
        return playwright_factory, TimeoutError
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise KakaoPlaywrightMissingError from exc

    def factory() -> _PlaywrightManager:
        return _PlaywrightManagerAdapter(sync_playwright())

    return factory, PlaywrightTimeoutError


def _is_login_url(url: str) -> bool:
    return "accounts.kakao.com" in url
