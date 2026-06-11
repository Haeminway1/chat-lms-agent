from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from chat_lms_agent.classcard_direct_audio import (
    ClasscardCard,
    card_mismatches,
    cards_from_payload,
    mismatch_report,
    sets_from_payload,
)
from chat_lms_agent.classcard_direct_browser import default_credentials_path, login_classcard
from chat_lms_agent.classcard_direct_scripts import (
    DIRECT_UPLOAD_SCRIPT,
    READ_CLASS_SETS_SCRIPT,
    READ_STUDY_DATA_SCRIPT,
    SUGGEST_AUDIO_SCRIPT,
)


@dataclass(frozen=True, slots=True)
class DirectPart:
    index: int
    assigned_date: str
    tsv_path: Path
    site_title: str
    word_count: int


@dataclass(frozen=True, slots=True)
class DirectRun:
    checkpoint_path: Path
    class_idx: str
    credentials_path: Path
    profile_dir: Path
    student: str
    run_id: str
    parts: tuple[DirectPart, ...]


class DirectUploadError(RuntimeError):
    pass


WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def upload_missing_parts(run: DirectRun) -> dict[str, str | list[int] | list[dict[str, str | int | bool]]]:
    from playwright.sync_api import sync_playwright

    completed: list[int] = []
    uploaded: list[dict[str, str | int | bool]] = []
    with sync_playwright() as runtime:
        context = runtime.chromium.launch_persistent_context(str(run.profile_dir), headless=True)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(20_000)
            login_classcard(page, run.credentials_path)
            for part in run.parts:
                _write_checkpoint(run, "uploading", completed, current_part=part.index)
                rows = _read_tsv(part.tsv_path)
                if len(rows) != part.word_count:
                    raise DirectUploadError(f"word count mismatch for {part.tsv_path}")
                existing_set_id = _find_existing_set_id(page, run.class_idx, part)
                if existing_set_id is not None:
                    expected_cards = _expected_cards_for_rows(page, rows)
                    _verify_set_cards(page, existing_set_id, expected_cards, label=part.site_title)
                    completed.append(part.index)
                    uploaded.append(
                        {
                            "index": part.index,
                            "status": "already_present",
                            "title": part.site_title,
                            "set_idx": existing_set_id,
                            "word_count": part.word_count,
                        }
                    )
                    continue
                result = _upload_part(page, run.class_idx, part.site_title, rows)
                _verify_set_cards(page, str(result["set_idx"]), result["expected_cards"], label=part.site_title)
                if _find_existing_set_id(page, run.class_idx, part) is None:
                    raise DirectUploadError(f"upload verification failed after addclass3: {part.site_title}")
                completed.append(part.index)
                uploaded.append(
                    {
                        "index": part.index,
                        "status": "uploaded",
                        "title": part.site_title,
                        "set_idx": str(result["set_idx"]),
                        "word_count": part.word_count,
                    }
                )
                _write_checkpoint(run, "part_completed", completed, current_part=part.index)
            _write_checkpoint(run, "completed", completed, current_part=None)
        finally:
            context.close()
    return {"status": "completed", "completed_indexes": completed, "uploaded": uploaded}


def _load_run(checkpoint: str, class_url: str, credentials: str | None, profile_dir: str | None) -> DirectRun:
    checkpoint_path = Path(checkpoint)
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    manifest = _local_path(str(payload["manifest_path"]))
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    student = str(manifest_payload["student"])
    parts = tuple(_part_from_payload(student, part) for part in manifest_payload["parts"])
    return DirectRun(
        checkpoint_path=checkpoint_path,
        class_idx=_class_idx(class_url),
        credentials_path=Path(credentials) if credentials else default_credentials_path(),
        profile_dir=Path(profile_dir) if profile_dir else Path.home() / ".chat_lms_agent" / "classcard-profile",
        student=student,
        run_id=str(payload.get("run_id", "")),
        parts=parts,
    )


def _part_from_payload(student: str, payload: dict[str, str | int]) -> DirectPart:
    assigned_date = str(payload["assigned_date"])
    word_count = int(payload["word_count"])
    site_title = str(payload.get("title") or f"{student} {_date_label(assigned_date)} 단어")
    return DirectPart(
        index=int(payload["index"]),
        assigned_date=assigned_date,
        tsv_path=_local_path(str(payload["tsv_path"])),
        site_title=site_title,
        word_count=word_count,
    )


def _class_idx(class_url: str) -> str:
    match = re.search(r"/ClassMain/(\d+)", class_url)
    if match is None:
        raise DirectUploadError(f"ClassMain URL is required: {class_url}")
    return match.group(1)


def _local_path(value: str) -> Path:
    return Path(value.replace("\\", "/"))


def _date_label(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{parsed:%m/%d}({WEEKDAYS[parsed.weekday()]})"


def _read_tsv(path: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        cells = line.split("\t")
        front = cells[0].strip()
        back = cells[1].strip() if len(cells) > 1 else ""
        if not front or not back:
            raise DirectUploadError(f"blank Classcard cell in {path}: {line}")
        rows.append((front, back))
    return rows


def _part_exists(page, class_idx: str, part: DirectPart) -> bool:
    page.goto(f"https://www.classcard.net/ClassMain/{class_idx}", wait_until="domcontentloaded")
    text = page.locator("body").inner_text(timeout=20_000)
    normalized = " ".join(text.split())
    expected = f"{part.site_title}{part.word_count} 카드"
    spaced = f"{part.site_title} {part.word_count} 카드"
    compact = normalized.replace(" ", "")
    return expected.replace(" ", "") in compact or spaced in normalized


def _find_existing_set_id(page, class_idx: str, part: DirectPart) -> str | None:
    page.goto(f"https://www.classcard.net/ClassMain/{class_idx}", wait_until="domcontentloaded")
    payload = page.evaluate(READ_CLASS_SETS_SCRIPT, {"title": part.site_title, "wordCount": part.word_count})
    compact_title = part.site_title.replace(" ", "")
    for summary in sets_from_payload(payload):
        compact_text = summary.text.replace(" ", "")
        if compact_title in compact_text and str(part.word_count) in compact_text:
            return summary.set_idx
    if _part_exists(page, class_idx, part):
        raise DirectUploadError(f"found existing set but could not resolve set id: {part.site_title}")
    return None


def _expected_cards_for_rows(page, rows: list[tuple[str, str]]) -> tuple[ClasscardCard, ...]:
    page.goto("https://www.classcard.net/CreateWord", wait_until="domcontentloaded")
    page.wait_for_selector("#setForm", state="attached", timeout=20_000)
    result = page.evaluate(SUGGEST_AUDIO_SCRIPT, {"rows": rows})
    if result["stage"] != "completed":
        raise DirectUploadError(json.dumps(result, ensure_ascii=False))
    return cards_from_payload(result["cards"])


def _read_set_cards(page, set_idx: str) -> tuple[ClasscardCard, ...]:
    page.goto(f"https://www.classcard.net/set/{set_idx}", wait_until="domcontentloaded")
    page.wait_for_function("() => Boolean(window.study_data)", timeout=20_000)
    payload = page.evaluate(READ_STUDY_DATA_SCRIPT)
    return cards_from_payload(payload)


def _verify_set_cards(page, set_idx: str, expected_cards: tuple[ClasscardCard, ...], *, label: str) -> None:
    actual_cards = _read_set_cards(page, set_idx)
    mismatches = card_mismatches(expected_cards, actual_cards)
    if mismatches:
        raise DirectUploadError(f"Classcard audio verification failed for {label}: {mismatch_report(mismatches)}")


def _upload_part(page, class_idx: str, title: str, rows: list[tuple[str, str]]) -> dict[str, str | tuple[ClasscardCard, ...]]:
    page.goto("https://www.classcard.net/CreateWord", wait_until="domcontentloaded")
    page.wait_for_selector("#setForm", state="attached", timeout=20_000)
    result = page.evaluate(DIRECT_UPLOAD_SCRIPT, {"classIdx": class_idx, "rows": rows, "title": title})
    if result["stage"] != "completed":
        raise DirectUploadError(json.dumps(result, ensure_ascii=False))
    return {"set_idx": str(result["set_idx"]), "expected_cards": cards_from_payload(result["cards"])}


def _write_checkpoint(run: DirectRun, status: str, completed: list[int], *, current_part: int | None) -> None:
    payload = json.loads(run.checkpoint_path.read_text(encoding="utf-8"))
    payload["status"] = status
    payload["completed_indexes"] = completed
    payload["current_part"] = current_part
    payload["missing_indexes"] = [part.index for part in run.parts if part.index not in completed]
    run.checkpoint_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")




