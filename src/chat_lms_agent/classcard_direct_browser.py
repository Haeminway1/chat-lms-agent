from __future__ import annotations

import json
from pathlib import Path


def default_credentials_path() -> Path:
    return Path.home() / ".chat_lms_agent" / "classcard_credentials.json"


def login_classcard(page, credentials_path: Path) -> None:
    creds = json.loads(credentials_path.read_text(encoding="utf-8"))
    page.goto("https://www.classcard.net/Main", wait_until="domcontentloaded")
    if "/Login" not in page.url:
        return
    username = str(creds["username"])
    password = str(creds["password"])
    if page.locator("input[name='login_id']").count() > 0:
        page.locator("input[name='login_id']").first.fill(username)
    else:
        page.locator("input[type='text']").first.fill(username)
    if page.locator("input[name='login_pwd']").count() > 0:
        page.locator("input[name='login_pwd']").first.fill(password)
    else:
        page.locator("input[type='password']").first.fill(password)
    page.locator("input[name='login_pwd'], input[type='password']").first.press("Enter")
    page.wait_for_url(lambda url: "/Login" not in url, timeout=30_000, wait_until="domcontentloaded")
