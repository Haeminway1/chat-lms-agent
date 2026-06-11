from __future__ import annotations

import json
from pathlib import Path

from chat_lms_agent.classcard_direct_audio import cards_from_payload
from chat_lms_agent.classcard_direct_browser import default_credentials_path, login_classcard
from chat_lms_agent.classcard_direct_scripts import REPAIR_AUDIO_SCRIPT
from chat_lms_agent.classcard_direct_upload import DirectUploadError, _verify_set_cards


def repair_set_audio_paths(set_id: str, credentials: str | None = None, profile_dir: str | None = None) -> dict[str, str | int]:
    from playwright.sync_api import sync_playwright

    credentials_path = Path(credentials) if credentials else default_credentials_path()
    profile_path = Path(profile_dir) if profile_dir else Path.home() / ".chat_lms_agent" / "classcard-wsl-profile"
    with sync_playwright() as runtime:
        context = runtime.chromium.launch_persistent_context(str(profile_path), headless=True)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(20_000)
            login_classcard(page, credentials_path)
            page.goto(f"https://www.classcard.net/CreateWord/{set_id}", wait_until="domcontentloaded")
            page.wait_for_selector("#setForm", state="attached", timeout=20_000)
            result = page.evaluate(REPAIR_AUDIO_SCRIPT, {"setId": set_id})
            if result["stage"] != "completed":
                raise DirectUploadError(json.dumps(result, ensure_ascii=False))
            expected_cards = cards_from_payload(result["cards"])
            _verify_set_cards(page, str(result["set_idx"]), expected_cards, label=f"set {set_id}")
        finally:
            context.close()
    return {"status": "completed", "set_idx": set_id, "word_count": len(expected_cards)}
