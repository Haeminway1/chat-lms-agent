from __future__ import annotations

from pathlib import Path

from chat_lms_agent.classcard_browser import (
    ClasscardAutomationError,
    ClasscardBrowserOptions,
    PlaywrightClasscardPage,
)
from chat_lms_agent.classcard_login import load_classcard_credentials


def read_class_page_text_with_playwright(
    class_url: str,
    *,
    options: ClasscardBrowserOptions | None = None,
) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ClasscardAutomationError("Playwright is required: py -3 -m pip install playwright && py -3 -m playwright install chromium") from exc
    selected = options or ClasscardBrowserOptions()
    profile_dir = selected.profile_dir or Path.home() / ".chat_lms_agent" / "classcard-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as runtime:
        context = runtime.chromium.launch_persistent_context(
            str(profile_dir),
            headless=not selected.headed,
            slow_mo=selected.slow_mo_ms,
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(10_000)
        adapter = PlaywrightClasscardPage(page, selected.credentials or load_classcard_credentials())
        try:
            page.goto(class_url, wait_until="domcontentloaded")
            adapter.ensure_logged_in()
            page.goto(class_url, wait_until="domcontentloaded")
            page.wait_for_load_state("domcontentloaded")
            return page.locator("body").inner_text(timeout=10_000)
        finally:
            context.close()
