from __future__ import annotations

import json
from pathlib import Path

from chat_lms_agent.classcard_browser import ClasscardBrowserOptions
from chat_lms_agent.classcard_browser_verify import read_class_page_text_with_playwright
from chat_lms_agent.classcard_plan import build_upload_plan, parse_classcard_mode
from chat_lms_agent.classcard_verification import (
    ClasscardVerificationResult,
    record_verification_result,
    verify_class_page_text,
)


def verify_checkpoint_from_page_text(checkpoint_path: str | Path, page_text: str) -> ClasscardVerificationResult:
    checkpoint = Path(checkpoint_path)
    payload = _checkpoint_payload(checkpoint)
    db_path = Path(payload["db_path"])
    run_id = payload["run_id"]
    plan = build_upload_plan(
        db_path,
        payload["student"],
        lesson_date=payload["lesson_date"],
        mode=parse_classcard_mode(payload["mode"]),
    )
    verification = verify_class_page_text(plan, page_text)
    record_verification_result(plan, checkpoint, db_path, run_id, verification)
    return verification


def verify_checkpoint_with_playwright(
    checkpoint_path: str | Path,
    class_url: str,
    *,
    browser_options: ClasscardBrowserOptions | None = None,
) -> ClasscardVerificationResult:
    page_text = read_class_page_text_with_playwright(class_url, options=browser_options)
    return verify_checkpoint_from_page_text(checkpoint_path, page_text)


def _checkpoint_payload(checkpoint: Path) -> dict[str, str]:
    raw = json.loads(checkpoint.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise LookupError("Classcard checkpoint must be a JSON object")
    payload = {str(key): str(value) for key, value in raw.items() if value is not None}
    for key in ("db_path", "run_id", "student", "lesson_date", "mode"):
        if not payload.get(key):
            raise LookupError(f"Classcard checkpoint is missing {key}")
    return payload
