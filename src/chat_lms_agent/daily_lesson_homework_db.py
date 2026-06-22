from __future__ import annotations

import sqlite3
from datetime import date
from typing import TYPE_CHECKING, cast

from chat_lms_agent.daily_lesson_homework_sheet import clean

if TYPE_CHECKING:
    from pathlib import Path

WEEKDAY_CODES = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


def connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def today_sessions(
    conn: sqlite3.Connection,
    lesson_date: str,
    class_codes: set[str],
) -> dict[str, sqlite3.Row]:
    if not class_codes:
        return {}
    rows = cast(
        "list[sqlite3.Row]",
        conn.execute(
            """
        SELECT s.id, s.class_id, s.subject, c.canonical_name AS class_name
        FROM sessions s
        JOIN classes c ON c.id = s.class_id
        WHERE s.session_date = ?
          AND s.session_kind = 'main'
        ORDER BY s.id
        """,
            (lesson_date,),
        ).fetchall(),
    )
    return {
        clean(cast("object", row["class_name"])): row
        for row in rows
        if clean(cast("object", row["class_name"])) in class_codes
    }


def session_records(conn: sqlite3.Connection, session_id: int) -> tuple[sqlite3.Row, ...]:
    rows = cast(
        "list[sqlite3.Row]",
        conn.execute(
            """
            SELECT r.session_id, st.id AS student_id, st.canonical_name AS student_name,
                   r.attendance, r.homework_score
            FROM student_session_records r
            JOIN students st ON st.id = r.student_id
            WHERE r.session_id = ?
            ORDER BY st.canonical_name
            """,
            (session_id,),
        ).fetchall(),
    )
    return tuple(rows)


def previous_homework(
    conn: sqlite3.Connection,
    class_id: int,
    lesson_date: str,
    subject: str,
) -> sqlite3.Row | None:
    rows = cast(
        "list[sqlite3.Row]",
        conn.execute(
            """
        SELECT id, class_id, session_date, subject, homework
        FROM sessions
        WHERE class_id = ?
          AND session_kind = 'main'
          AND session_date < ?
          AND trim(coalesce(homework, '')) <> ''
        ORDER BY session_date DESC, id DESC
        """,
            (class_id, lesson_date),
        ).fetchall(),
    )
    for row in rows:
        candidate = session_subject(
            conn,
            class_id,
            clean(cast("object", row["session_date"])),
            clean(cast("object", row["subject"])),
        )
        if candidate.lower() == subject.lower():
            return row
    return None


def session_subject(conn: sqlite3.Connection, class_id: int, lesson_date: str, subject: str) -> str:
    if subject:
        return subject
    weekday = WEEKDAY_CODES[date.fromisoformat(lesson_date).weekday()]
    row = cast(
        "sqlite3.Row | None",
        conn.execute(
            """
        SELECT subject
        FROM class_schedule_entries
        WHERE class_id = ?
          AND weekday = ?
          AND session_kind = 'main'
          AND status = 'active'
        ORDER BY id
        LIMIT 1
        """,
            (class_id, weekday),
        ).fetchone(),
    )
    return clean(cast("object", row["subject"])) if row is not None else ""
