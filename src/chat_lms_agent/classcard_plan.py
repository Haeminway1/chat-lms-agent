from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from typing import assert_never

from chat_lms_agent.classcard_db import WordRecord, _student_id, connect, load_json


class ClasscardMode(StrEnum):
    ALL = "all"
    N_DAYS = "n_days"
    AB_REPEAT = "ab_repeat"


@dataclass(frozen=True, slots=True)
class UploadPart:
    index: int
    label: str
    title: str
    assigned_date: str
    words: tuple[WordRecord, ...]

    @property
    def tsv(self) -> str:
        return "\n".join(f"{_cell(word.headword)}\t{_cell(word.meaning)}" for word in self.words) + "\n"


@dataclass(frozen=True, slots=True)
class UploadPlan:
    student_id: int
    student_name: str
    target_class_name: str
    lesson_id: int
    lesson_date: str
    mode: ClasscardMode
    parts: tuple[UploadPart, ...]

    @property
    def word_count(self) -> int:
        return sum(len(part.words) for part in self.parts)


@dataclass(frozen=True, slots=True)
class _LessonRef:
    lesson_id: int
    lesson_date: date


_MODE_ALIASES = {
    "all": ClasscardMode.ALL,
    "전체": ClasscardMode.ALL,
    "daily": ClasscardMode.N_DAYS,
    "n": ClasscardMode.N_DAYS,
    "n_days": ClasscardMode.N_DAYS,
    "n일": ClasscardMode.N_DAYS,
    "repeat": ClasscardMode.AB_REPEAT,
    "ab": ClasscardMode.AB_REPEAT,
    "ab_repeat": ClasscardMode.AB_REPEAT,
    "ab반복": ClasscardMode.AB_REPEAT,
}

_WEEKDAY_ALIASES = {
    "MON": 0,
    "MONDAY": 0,
    "월": 0,
    "TUE": 1,
    "TUESDAY": 1,
    "화": 1,
    "WED": 2,
    "WEDNESDAY": 2,
    "수": 2,
    "THU": 3,
    "THURSDAY": 3,
    "목": 3,
    "FRI": 4,
    "FRIDAY": 4,
    "금": 4,
    "SAT": 5,
    "SATURDAY": 5,
    "토": 5,
    "SUN": 6,
    "SUNDAY": 6,
    "일": 6,
}


def build_upload_plan(
    db_path: str | Path,
    student: str,
    *,
    lesson_date: str | None = None,
    mode: ClasscardMode | None = None,
    span_days: int | None = None,
) -> UploadPlan:
    with closing(connect(db_path)) as conn:
        student_id = _student_id(conn, student)
        student_name, attrs = _student_profile(conn, student_id)
        lesson = _lesson_for_upload(conn, student_id, lesson_date)
        words = _lesson_words(conn, lesson.lesson_id)
        resolved_mode = mode or _mode_from_attrs(attrs)
        target_class_name = attrs.get("classcard_class_name") or student_name
        fallback_span = span_days or _positive_int(attrs.get("classcard_span_days")) or 6
        weekdays = _active_weekdays(conn, student_id)
    parts = _parts_for_mode(student_name, lesson.lesson_date, resolved_mode, words, weekdays, fallback_span)
    return UploadPlan(student_id, student_name, target_class_name, lesson.lesson_id, lesson.lesson_date.isoformat(), resolved_mode, parts)


def parse_classcard_mode(value: str) -> ClasscardMode:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    mode = _MODE_ALIASES.get(normalized)
    if mode is None:
        raise LookupError(f"unknown Classcard mode: {value}")
    return mode


def _student_profile(conn, student_id: int) -> tuple[str, dict[str, str]]:
    row = conn.execute("SELECT canonical_name, attrs_json FROM tutoring_students WHERE id = ?", (student_id,)).fetchone()
    if row is None:
        raise LookupError(f"unknown tutoring student id: {student_id}")
    return str(row["canonical_name"]), load_json(str(row["attrs_json"]))


def _mode_from_attrs(attrs: dict[str, str]) -> ClasscardMode:
    raw = attrs.get("classcard_mode")
    if raw:
        return parse_classcard_mode(raw)
    return ClasscardMode.ALL


def _lesson_for_upload(conn, student_id: int, lesson_date: str | None) -> _LessonRef:
    params: tuple[int, ...] | tuple[int, str]
    where = "l.student_id = ?"
    params = (student_id,)
    if lesson_date:
        where += " AND l.lesson_date = ?"
        params = (student_id, lesson_date)
    row = conn.execute(
        f"""
        SELECT l.id, l.lesson_date, COUNT(lw.id) AS word_count
        FROM tutoring_lessons l
        LEFT JOIN tutoring_lesson_words lw ON lw.lesson_id = l.id
        WHERE {where}
        GROUP BY l.id
        HAVING word_count > 0
        ORDER BY l.lesson_date DESC, word_count DESC, l.id DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    if row is None:
        raise LookupError("no vocabulary lesson words found for Classcard upload")
    return _LessonRef(int(row["id"]), date.fromisoformat(str(row["lesson_date"])))


def _lesson_words(conn, lesson_id: int) -> tuple[WordRecord, ...]:
    rows = conn.execute(
        """
        SELECT e.id AS entry_id, e.canonical_headword AS headword,
               ifnull(
                   (
                       SELECT group_concat(definition, '; ')
                       FROM (
                           SELECT definition
                           FROM tutoring_word_senses
                           WHERE word_entry_id = e.id
                             AND trim(definition) <> ''
                           ORDER BY id
                       )
                   ),
                   ''
               ) AS meaning
        FROM tutoring_lesson_words lw
        JOIN tutoring_word_entries e ON e.id = lw.word_entry_id
        WHERE lw.lesson_id = ?
        ORDER BY lw.id
        """,
        (lesson_id,),
    ).fetchall()
    return tuple(WordRecord(int(row["entry_id"]), str(row["headword"]), str(row["meaning"])) for row in rows)


def _active_weekdays(conn, student_id: int) -> tuple[int, ...]:
    rows = conn.execute(
        "SELECT weekday, day_label FROM tutoring_schedules WHERE student_id = ? AND status = 'active'",
        (student_id,),
    ).fetchall()
    weekdays: list[int] = []
    for row in rows:
        weekday = _weekday_index(str(row["weekday"] or row["day_label"] or ""))
        if weekday is not None and weekday not in weekdays:
            weekdays.append(weekday)
    return tuple(weekdays)


def _parts_for_mode(
    student_name: str,
    lesson_day: date,
    mode: ClasscardMode,
    words: tuple[WordRecord, ...],
    weekdays: tuple[int, ...],
    fallback_span_days: int,
) -> tuple[UploadPart, ...]:
    match mode:
        case ClasscardMode.ALL:
            return (UploadPart(0, "전체", f"{student_name} {lesson_day.isoformat()}", lesson_day.isoformat(), words),)
        case ClasscardMode.N_DAYS:
            dates = _n_day_dates(lesson_day, weekdays, fallback_span_days)
            return tuple(
                UploadPart(index, f"D{index + 1}", f"{student_name} {assigned_date}", assigned_date, part_words)
                for index, (assigned_date, part_words) in enumerate(zip(dates, _split_evenly(words, len(dates)), strict=True))
            )
        case ClasscardMode.AB_REPEAT:
            chunks = _split_evenly(words, 2)
            return tuple(
                UploadPart(index, label, f"{student_name} {lesson_day.isoformat()} {label}", lesson_day.isoformat(), part_words)
                for index, (label, part_words) in enumerate(zip(("A", "B"), chunks, strict=True))
            )
        case unreachable:
            assert_never(unreachable)


def _n_day_dates(lesson_day: date, weekdays: tuple[int, ...], fallback_span_days: int) -> tuple[str, ...]:
    next_lesson = _next_lesson_date(lesson_day, weekdays)
    day_count = max((next_lesson - lesson_day).days - 1, 1) if next_lesson else max(fallback_span_days, 1)
    return tuple((lesson_day + timedelta(days=offset)).isoformat() for offset in range(1, day_count + 1))


def _next_lesson_date(lesson_day: date, weekdays: tuple[int, ...]) -> date | None:
    candidates: list[date] = []
    for weekday in weekdays:
        delta = (weekday - lesson_day.weekday()) % 7
        candidates.append(lesson_day + timedelta(days=delta or 7))
    return min(candidates) if candidates else None


def _split_evenly(words: tuple[WordRecord, ...], count: int) -> tuple[tuple[WordRecord, ...], ...]:
    base, remainder = divmod(len(words), count)
    chunks: list[tuple[WordRecord, ...]] = []
    cursor = 0
    for index in range(count):
        size = base + (1 if index < remainder else 0)
        chunks.append(words[cursor : cursor + size])
        cursor += size
    return tuple(chunks)


def _weekday_index(value: str) -> int | None:
    normalized = value.strip().upper()
    if normalized in _WEEKDAY_ALIASES:
        return _WEEKDAY_ALIASES[normalized]
    raw = value.strip()
    if raw in _WEEKDAY_ALIASES:
        return _WEEKDAY_ALIASES[raw]
    return None


def _positive_int(value: str | None) -> int | None:
    if not value:
        return None
    parsed = int(value)
    return parsed if parsed > 0 else None


def _cell(value: str) -> str:
    return " ".join(value.replace("\t", " ").splitlines()).strip()
