from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent.classcard_db import connect, load_json
from chat_lms_agent.classcard_direct_browser import default_credentials_path, login_classcard

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

_CLASS_IDX_RE = re.compile(r"/ClassMain/(\d+)")
_INT_RE = re.compile(r"-?\d+")
_LOW_START_RATIO = 0.25
_COMPLETE_MEM = 100
_STRONG_PROGRESS = 90
_GOOD_PROGRESS = 80
_LOW_PROGRESS = 50
_LOW_MEM_PROGRESS = 60
_GOOD_TEST_SCORE = 85
_MIN_TREND_POINTS = 4
_TREND_DELTA_THRESHOLD = 20


@dataclass(frozen=True, slots=True)
class LiveStudentTarget:
    student_id: int
    student_name: str
    public_id: str
    class_idx: str
    class_url: str


@dataclass(frozen=True, slots=True)
class LiveClasscardSet:
    set_idx: str
    title: str
    card_count: int
    display_order: int


def live_study_report(
    db_path: str | Path,
    *,
    student: str | None = None,
    limit: int = 12,
    class_url: str | None = None,
    profile_dir: str | Path | None = None,
    credentials: str | Path | None = None,
) -> dict[str, JsonValue]:
    targets = _targets(db_path, student=student, class_url=class_url)
    from playwright.sync_api import sync_playwright

    profile = Path(profile_dir) if profile_dir else Path.home() / ".chat_lms_agent" / "classcard-profile"
    credentials_path = Path(credentials) if credentials else default_credentials_path()
    students: list[JsonValue] = []
    with sync_playwright() as runtime:
        context = runtime.chromium.launch_persistent_context(str(profile), headless=True)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(30_000)
            login_classcard(page, credentials_path)
            for target in targets:
                sets = _class_sets(page, target.class_idx)
                selected_sets = sets[:limit] if limit > 0 else sets
                reports = [
                    _set_report(page, target, item)
                    for item in selected_sets
                ]
                students.append(_student_payload(target, sets, reports, limit))
        finally:
            context.close()
    return {
        "status": "PASS",
        "classcard_status": "live_study_report",
        "students": students,
    }


def summarize_live_sets(
    set_reports: list[dict[str, JsonValue]],
) -> dict[str, JsonValue]:
    total_cards = sum(_int_value(item.get("card_count")) for item in set_reports)
    if total_cards <= 0:
        return {
            "set_count": len(set_reports),
            "card_count": 0,
            "mem_progress_pct": None,
            "mem_completion_pct": None,
            "recall_progress_pct": None,
            "spell_progress_pct": None,
            "test_average": None,
            "completed_sets": 0,
            "not_started_sets": len(set_reports),
            "style": "데이터 없음",
            "trend": "판단 보류",
        }
    mem_progress = _weighted_metric(set_reports, "mem_score", cap=None)
    mem_completion = _weighted_metric(set_reports, "mem_score", cap=100)
    recall_progress = _weighted_metric(set_reports, "recall_score", cap=None)
    spell_progress = _weighted_metric(set_reports, "spell_score", cap=None)
    test_average = _weighted_metric(set_reports, "test_score", cap=100, ignore_none=True)
    completed_sets = sum(1 for item in set_reports if bool(item.get("learn_completed")))
    not_started_sets = sum(1 for item in set_reports if _int_value(item.get("mem_score")) <= 0)
    return {
        "set_count": len(set_reports),
        "card_count": total_cards,
        "mem_progress_pct": _round_or_none(mem_progress),
        "mem_completion_pct": _round_or_none(mem_completion),
        "recall_progress_pct": _round_or_none(recall_progress),
        "spell_progress_pct": _round_or_none(spell_progress),
        "test_average": _round_or_none(test_average),
        "completed_sets": completed_sets,
        "not_started_sets": not_started_sets,
        "style": _style_label(mem_progress, recall_progress, spell_progress, test_average, not_started_sets, len(set_reports)),
        "trend": _trend_label(set_reports),
    }


def _targets(
    db_path: str | Path,
    *,
    student: str | None,
    class_url: str | None,
) -> tuple[LiveStudentTarget, ...]:
    with closing(connect(db_path)) as conn:
        rows = _student_rows(conn, student)
    targets: list[LiveStudentTarget] = []
    for row in rows:
        attrs = load_json(str(row["attrs_json"]))
        resolved_url = class_url or attrs.get("classcard_class_url") or ""
        class_idx = attrs.get("classcard_class_id") or _class_idx(resolved_url)
        if not class_idx:
            continue
        if not resolved_url:
            resolved_url = f"https://www.classcard.net/ClassMain/{class_idx}"
        targets.append(
            LiveStudentTarget(
                student_id=int(row["id"]),
                student_name=str(row["canonical_name"]),
                public_id=str(row["public_id"]),
                class_idx=class_idx,
                class_url=resolved_url,
            ),
        )
    return tuple(targets)


def _student_rows(conn: sqlite3.Connection, student: str | None) -> list[sqlite3.Row]:
    if student:
        row = conn.execute(
            """
            SELECT id, public_id, canonical_name, attrs_json
            FROM tutoring_students
            WHERE canonical_name = ? OR public_id = ?
            """,
            (student, student),
        ).fetchone()
        if row is None:
            raise LookupError(f"unknown tutoring student: {student}")
        return [row]
    return list(
        conn.execute(
            """
            SELECT id, public_id, canonical_name, attrs_json
            FROM tutoring_students
            WHERE active = 1
            ORDER BY id
            """,
        ).fetchall(),
    )


def _class_idx(value: str) -> str:
    match = _CLASS_IDX_RE.search(value)
    return match.group(1) if match else ""


def _class_sets(page, class_idx: str) -> tuple[LiveClasscardSet, ...]:
    page.goto(f"https://www.classcard.net/ClassReports/set/{class_idx}", wait_until="domcontentloaded")
    page.wait_for_timeout(1_500)
    payload = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('.class-report-panel')).map((panel, index) => {
          const link = panel.querySelector('a[href^="/set/"]');
          const titleNode = link?.querySelector('span') || link;
          return {
            set_idx: String(panel.dataset.idx || link?.getAttribute('href')?.match(/\\/set\\/(\\d+)/)?.[1] || ''),
            title: String(titleNode?.innerText || '').trim(),
            card_count: Number(panel.dataset.cnt || 0),
            display_order: index,
          };
        }).filter((item) => item.set_idx && item.title);
        """,
    )
    return tuple(
        LiveClasscardSet(
            set_idx=str(item.get("set_idx", "")),
            title=str(item.get("title", "")),
            card_count=_int_value(item.get("card_count")),
            display_order=_int_value(item.get("display_order")),
        )
        for item in payload
        if isinstance(item, dict)
    )


def _set_report(page, target: LiveStudentTarget, item: LiveClasscardSet) -> dict[str, JsonValue]:
    payload = page.evaluate(
        """
        async ({classIdx, setIdx}) => {
          const body = new URLSearchParams({
            class_idx: String(classIdx),
            set_idx: String(setIdx),
            score_sort: '1',
            mem_sort: '1',
            b_s_idx: '-1',
            b_s_type: '-1',
          });
          const response = await fetch('/ReportAsync/getClassSetUserReport_v2', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
              'X-Requested-With': 'XMLHttpRequest',
            },
            body,
          });
          return await response.json();
        }
        """,
        {"classIdx": target.class_idx, "setIdx": item.set_idx},
    )
    records = payload.get("set_user_list") if isinstance(payload, dict) else []
    user = _matching_user(records if isinstance(records, list) else [], target.student_name)
    report = _empty_set_report(item)
    if user is None:
        report["student_found"] = False
        return report
    report.update(
        {
            "student_found": True,
            "classcard_user_name": str(user.get("user_name", "")),
            "classcard_login_id": str(user.get("login_id", "")),
            "mem_score": _int_or_none(user.get("mem_score")),
            "recall_score": _int_or_none(user.get("recall_score")),
            "spell_score": _int_or_none(user.get("spell_score")),
            "test_score": _int_or_none(user.get("test_score")),
            "mem_date": _none_if_blank(user.get("mem_date")),
            "recall_date": _none_if_blank(user.get("recall_date")),
            "spell_date": _none_if_blank(user.get("spell_date")),
            "test_date": _none_if_blank(user.get("submit_date")),
            "learn_completed": bool(user.get("learn_completed")),
            "mem_learn_card_count": _int_value(user.get("mem_learn_card_cnt")),
            "recall_learn_card_count": _int_value(user.get("recall_learn_card_cnt")),
            "spell_learn_card_count": _int_value(user.get("spell_learn_card_cnt")),
            "test_learn_card_count": _int_value(user.get("test_learn_card_cnt")),
        },
    )
    return report


def _empty_set_report(item: LiveClasscardSet) -> dict[str, JsonValue]:
    return {
        "set_idx": item.set_idx,
        "title": item.title,
        "card_count": item.card_count,
        "display_order": item.display_order,
        "student_found": None,
        "mem_score": None,
        "recall_score": None,
        "spell_score": None,
        "test_score": None,
        "learn_completed": False,
    }


def _matching_user(records: list[JsonValue], student_name: str) -> dict[str, JsonValue] | None:
    candidates: list[dict[str, JsonValue]] = [item for item in records if isinstance(item, dict)]
    for item in candidates:
        if str(item.get("user_name", "")).strip() == student_name:
            return item
    students = [
        item
        for item in candidates
        if str(item.get("user_type", "")) == "2"
        and str(item.get("user_name", "")).strip()
        and "샘플" not in str(item.get("user_name", ""))
    ]
    if len(students) == 1:
        return students[0]
    active = [item for item in students if _int_value(item.get("learn_start")) > 0]
    return active[0] if active else (students[0] if students else None)


def _student_payload(
    target: LiveStudentTarget,
    all_sets: tuple[LiveClasscardSet, ...],
    reports: list[dict[str, JsonValue]],
    limit: int,
) -> dict[str, JsonValue]:
    return {
        "student": target.student_name,
        "student_id": target.student_id,
        "public_id": target.public_id,
        "class_idx": target.class_idx,
        "class_url": target.class_url,
        "set_count_total": len(all_sets),
        "set_count_fetched": len(reports),
        "limit": limit,
        "summary": summarize_live_sets(reports),
        "sets": reports,
    }


def _weighted_metric(
    set_reports: list[dict[str, JsonValue]],
    key: str,
    *,
    cap: int | None,
    ignore_none: bool = False,
) -> float | None:
    numerator = 0.0
    denominator = 0
    for item in set_reports:
        score = _int_or_none(item.get(key))
        cards = _int_value(item.get("card_count"))
        if cards <= 0:
            continue
        if score is None:
            if ignore_none:
                continue
            score = 0
        if cap is not None:
            score = min(score, cap)
        numerator += cards * score
        denominator += cards
    return numerator / denominator if denominator else None


def _style_label(
    mem: float | None,
    recall: float | None,
    spell: float | None,
    test: float | None,
    not_started: int,
    total_sets: int,
) -> str:
    mem = mem or 0
    recall = recall or 0
    spell = spell or 0
    started_ratio = 0 if total_sets == 0 else (total_sets - not_started) / total_sets
    if started_ratio < _LOW_START_RATIO:
        return "미착수/초기 노출 부족형"
    if (
        mem >= _COMPLETE_MEM
        and recall >= _STRONG_PROGRESS
        and spell >= _STRONG_PROGRESS
        and (test is None or test >= _GOOD_TEST_SCORE)
    ):
        return "완성형 반복 암기"
    if mem >= _STRONG_PROGRESS and recall < _LOW_PROGRESS and spell < _LOW_PROGRESS:
        return "암기표시 선행형: 능동 회상 보강 필요"
    if mem >= _GOOD_PROGRESS and recall >= _GOOD_PROGRESS and spell < _LOW_PROGRESS:
        return "뜻 회상 우세형: 철자 보강 필요"
    if mem < _LOW_MEM_PROGRESS:
        return "암기 진입 부족형"
    return "부분 정착형"


def _trend_label(set_reports: list[dict[str, JsonValue]]) -> str:
    scored = [
        _int_value(item.get("mem_score"))
        for item in reversed(set_reports)
        if _int_or_none(item.get("mem_score")) is not None
    ]
    if len(scored) < _MIN_TREND_POINTS:
        return "판단 보류"
    mid = len(scored) // 2
    early = sum(scored[:mid]) / len(scored[:mid])
    recent = sum(scored[mid:]) / len(scored[mid:])
    delta = recent - early
    if delta >= _TREND_DELTA_THRESHOLD:
        return f"상승 추세(+{delta:.1f}%p)"
    if delta <= -_TREND_DELTA_THRESHOLD:
        return f"하락 추세({delta:.1f}%p)"
    return f"유지/완만한 변화({delta:+.1f}%p)"


def _int_value(value: JsonValue | object) -> int:
    parsed = _int_or_none(value)
    return parsed if parsed is not None else 0


def _int_or_none(value: JsonValue | object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    match = _INT_RE.search(text)
    return int(match.group(0)) if match else None


def _none_if_blank(value: JsonValue | object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _round_or_none(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None
