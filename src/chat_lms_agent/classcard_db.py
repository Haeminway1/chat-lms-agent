"""Minimal DB helpers for the ClassCard planning flow.

Extracted from the private predecessor repo's ``db.py``/``tutoring.py`` so
the ClassCard planner can read the teacher's profile database
(``<profile-root>/data/chat_lms.db``) without dragging the whole legacy data
layer along. The side-panel wordbook writes lesson words into the
``tutoring_*`` tables these queries read.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class WordRecord:
    entry_id: int | None
    headword: str
    meaning: str


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def dump_json(value: dict[str, str | int | float | bool | list[str] | None]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def load_json(text: str | None) -> dict[str, str]:
    if not text:
        return {}
    raw = json.loads(text)
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items() if value is not None}


def _student_id(conn: sqlite3.Connection, student: str) -> int:
    row = conn.execute(
        "SELECT id FROM tutoring_students WHERE canonical_name = ? OR public_id = ?",
        (student, student),
    ).fetchone()
    if row is None:
        raise LookupError(f"unknown tutoring student: {student}")
    return int(row["id"])


def _previous_words(conn: sqlite3.Connection, student_id: int) -> tuple[WordRecord, ...]:
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
        JOIN tutoring_lessons l ON l.id = lw.lesson_id
        JOIN tutoring_word_entries e ON e.id = lw.word_entry_id
        WHERE l.student_id = ?
          AND l.id = (SELECT id FROM tutoring_lessons WHERE student_id = ? ORDER BY lesson_date DESC, id DESC LIMIT 1)
        ORDER BY lw.id
        """,
        (student_id, student_id),
    ).fetchall()
    return tuple(
        WordRecord(int(row["entry_id"]), str(row["headword"]), str(row["meaning"]))
        for row in rows
    )
