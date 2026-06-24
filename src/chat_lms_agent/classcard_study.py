from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, cast

from chat_lms_agent.classcard_db import _student_id, connect, dump_json, load_json

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

_CORRECT_STATUSES = {
    "correct",
    "known",
    "learned",
    "memorized",
    "mastered",
    "pass",
    "passed",
    "done",
    "complete",
    "\uc554\uae30",
    "\uc644\ub8cc",
    "\uc815\ub2f5",
    "\ub9de\uc74c",
}
_WRONG_STATUSES = {
    "wrong",
    "incorrect",
    "unknown",
    "unlearned",
    "unmemorized",
    "fail",
    "failed",
    "miss",
    "missed",
    "\ubbf8\uc554\uae30",
    "\ubbf8\uc644\ub8cc",
    "\uc624\ub2f5",
    "\ud2c0\ub9bc",
}
_UNKNOWN_STATUSES = {
    "new",
    "notstarted",
    "not_started",
    "pending",
    "unseen",
    "\ud559\uc2b5\uc804",
}
_MASTERY_ACCURACY_THRESHOLD = 0.8


@dataclass(frozen=True, slots=True)
class StudyItem:
    word: str
    status: str
    correct_count: int
    wrong_count: int
    meaning: str | None = None

    @property
    def attempt_count(self) -> int:
        return self.correct_count + self.wrong_count

    @property
    def is_correct(self) -> bool:
        return self.correct_count > 0 and self.correct_count >= self.wrong_count


@dataclass(frozen=True, slots=True)
class StudyImportResult:
    student_id: int
    student_name: str
    observed_on: str
    dry_run: bool
    items_seen: int
    items_imported: int
    items_skipped: int
    score: int
    total: int
    pct: float | None
    quiz_session_id: int | None
    skipped_words: tuple[str, ...]


def import_study_result(
    db_path: str | Path,
    student: str,
    source_path: str | Path,
    *,
    observed_on: str,
    lesson_date: str | None = None,
    source_label: str | None = None,
    dry_run: bool = False,
    create_missing_words: bool = False,
) -> StudyImportResult:
    items = load_study_items(Path(source_path))
    with closing(connect(db_path)) as conn:
        student_id = _student_id(conn, student)
        student_name = _student_name(conn, student_id)
        lesson_id = _lesson_id(conn, student_id, lesson_date)
        matched: list[tuple[StudyItem, int]] = []
        skipped: list[str] = []
        for item in items:
            word_id = _word_entry_id(conn, item.word)
            if word_id is None and create_missing_words:
                word_id = _create_word_entry(conn, item)
            if word_id is None:
                skipped.append(item.word)
                continue
            matched.append((item, word_id))
        score = sum(item.correct_count for item, _ in matched)
        total = sum(item.attempt_count for item, _ in matched)
        pct = round(score / total * 100, 1) if total else None
        quiz_session_id: int | None = None
        if not dry_run:
            quiz_session_id = _insert_quiz_session(
                conn,
                student_id,
                lesson_id,
                observed_on,
                source_label,
                matched,
                skipped,
                score,
                total,
                pct,
            )
            for item, word_id in matched:
                if item.attempt_count > 0:
                    _insert_quiz_item(conn, quiz_session_id, word_id, item)
                _upsert_word_state(conn, student_id, word_id, item, observed_on, source_label)
            conn.commit()
        return StudyImportResult(
            student_id=student_id,
            student_name=student_name,
            observed_on=observed_on,
            dry_run=dry_run,
            items_seen=len(items),
            items_imported=len(matched),
            items_skipped=len(skipped),
            score=score,
            total=total,
            pct=pct,
            quiz_session_id=quiz_session_id,
            skipped_words=tuple(skipped),
        )


def load_study_items(path: Path) -> tuple[StudyItem, ...]:
    if not path.exists():
        raise FileNotFoundError(str(path))
    suffix = path.suffix.lower()
    if suffix == ".json":
        return _items_from_json(path)
    if suffix in {".csv", ".tsv", ".txt"}:
        return _items_from_delimited(path, delimiter="\t" if suffix == ".tsv" else None)
    raise ValueError(f"unsupported ClassCard study file type: {path.suffix}")


def study_summary(
    db_path: str | Path,
    *,
    student: str | None = None,
    limit: int = 10,
    mastery_threshold: int = 2,
) -> dict[str, JsonValue]:
    with closing(connect(db_path)) as conn:
        students = _students(conn, student)
        summaries: list[JsonValue] = [
            _student_summary(conn, row["id"], row["canonical_name"], limit, mastery_threshold)
            for row in students
        ]
    return {
        "status": "PASS",
        "classcard_status": "study_summary",
        "students": summaries,
    }


def due_words(
    db_path: str | Path,
    student: str,
    *,
    limit: int = 20,
    mastery_threshold: int = 2,
) -> dict[str, JsonValue]:
    with closing(connect(db_path)) as conn:
        student_id = _student_id(conn, student)
        student_name = _student_name(conn, student_id)
        rows = _word_rows(conn, student_id)
    due: list[JsonValue] = []
    for row in rows:
        item = _word_state_json(row, mastery_threshold)
        if item["status"] in {"new", "weak", "review"}:
            due.append(item)
    due.sort(key=_due_sort_key)
    return {
        "status": "PASS",
        "classcard_status": "study_due",
        "student": student_name,
        "due_words": due[:limit],
    }


def import_result_payload(result: StudyImportResult) -> dict[str, JsonValue]:
    return {
        "status": "PASS",
        "classcard_status": "study_imported" if not result.dry_run else "study_import_dry_run",
        "student": result.student_name,
        "student_id": result.student_id,
        "observed_on": result.observed_on,
        "dry_run": result.dry_run,
        "items_seen": result.items_seen,
        "items_imported": result.items_imported,
        "items_skipped": result.items_skipped,
        "score": result.score,
        "total": result.total,
        "pct": result.pct,
        "quiz_session_id": result.quiz_session_id,
        "skipped_words": list(result.skipped_words),
    }


def _items_from_json(path: Path) -> tuple[StudyItem, ...]:
    try:
        raw = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except JSONDecodeError as exc:
        raise ValueError(f"invalid ClassCard study JSON: {path}") from exc
    records: list[JsonValue] = []
    if isinstance(raw, list):
        records.extend(raw)
    elif isinstance(raw, dict):
        for key in ("items", "rows", "cards", "results"):
            value = raw.get(key)
            if isinstance(value, list):
                records.extend(value)
                break
        if not records:
            records.extend(_records_from_word_lists(raw))
    else:
        raise ValueError("ClassCard study JSON must be an object or list")
    return _items_from_records(records)


def _records_from_word_lists(raw: dict[str, JsonValue]) -> list[JsonValue]:
    specs = (
        ("memorized", "memorized"),
        ("known_words", "memorized"),
        ("correct_words", "correct"),
        ("wrong_words", "wrong"),
        ("unmemorized", "unmemorized"),
        ("unknown_words", "new"),
    )
    records: list[JsonValue] = []
    for key, status in specs:
        words = raw.get(key)
        if isinstance(words, list):
            records.extend({"word": str(word), "status": status} for word in words)
    return records


def _items_from_delimited(path: Path, *, delimiter: str | None) -> tuple[StudyItem, ...]:
    text = path.read_text(encoding="utf-8-sig")
    if delimiter is None:
        sample = text[:2048]
        delimiter = csv.Sniffer().sniff(sample, delimiters=",\t").delimiter if sample.strip() else ","
    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)
    return _items_from_records([dict(row) for row in reader])


def _items_from_records(records: list[JsonValue]) -> tuple[StudyItem, ...]:
    items: list[StudyItem] = []
    for record in records:
        if isinstance(record, str):
            item = _item_from_mapping({"word": record, "status": "new"})
        elif isinstance(record, dict):
            item = _item_from_mapping(record)
        else:
            item = None
        if item is not None:
            items.append(item)
    if not items:
        raise ValueError("no ClassCard study items found")
    return tuple(items)


def _item_from_mapping(record: dict[str, JsonValue]) -> StudyItem | None:
    word = _field(record, "word", "headword", "term", "card", "\ub2e8\uc5b4")
    if word is None or not word.strip():
        return None
    status = _field(record, "status", "result", "state", "\uc0c1\ud0dc", "\uacb0\uacfc") or ""
    correct_count = _int_field(record, "correct_count", "correct", "known_count")
    wrong_count = _int_field(record, "wrong_count", "wrong", "incorrect_count", "unknown_count")
    if correct_count is None or wrong_count is None:
        bool_value = _bool_field(record, "is_correct", "correct", "known", "memorized")
        if bool_value is not None:
            correct_count = 1 if bool_value else 0
            wrong_count = 0 if bool_value else 1
    if correct_count is None or wrong_count is None:
        parsed = _counts_from_status(status)
        correct_count = parsed[0] if correct_count is None else correct_count
        wrong_count = parsed[1] if wrong_count is None else wrong_count
    meaning = _field(record, "meaning", "definition", "\ub73b")
    return StudyItem(
        word=word.strip(),
        status=status.strip() or _status_from_counts(correct_count or 0, wrong_count or 0),
        correct_count=max(correct_count or 0, 0),
        wrong_count=max(wrong_count or 0, 0),
        meaning=meaning.strip() if meaning else None,
    )


def _field(record: dict[str, JsonValue], *names: str) -> str | None:
    normalized = {_normalize_key(str(key)): value for key, value in record.items()}
    for name in names:
        value = normalized.get(_normalize_key(name))
        if value is not None:
            return str(value)
    return None


def _int_field(record: dict[str, JsonValue], *names: str) -> int | None:
    value = _field(record, *names)
    if value is None or value == "":
        return None
    if value.strip().lower() in {"true", "false", "yes", "no", "y", "n"}:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _bool_field(record: dict[str, JsonValue], *names: str) -> bool | None:
    value = _field(record, *names)
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "correct", "known", "memorized"}:
        return True
    if normalized in {"0", "false", "no", "n", "wrong", "incorrect", "unknown"}:
        return False
    return None


def _counts_from_status(status: str) -> tuple[int, int]:
    normalized = _normalize_status(status)
    if normalized in _CORRECT_STATUSES:
        return (1, 0)
    if normalized in _WRONG_STATUSES:
        return (0, 1)
    if normalized in _UNKNOWN_STATUSES:
        return (0, 0)
    return (0, 0)


def _status_from_counts(correct_count: int, wrong_count: int) -> str:
    if correct_count > 0 and wrong_count == 0:
        return "memorized"
    if wrong_count > 0:
        return "wrong"
    return "new"


def _normalize_key(value: str) -> str:
    return "".join(char for char in value.strip().lower() if char.isalnum())


def _normalize_status(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _student_name(conn: sqlite3.Connection, student_id: int) -> str:
    row = conn.execute("SELECT canonical_name FROM tutoring_students WHERE id = ?", (student_id,)).fetchone()
    if row is None:
        raise LookupError(f"unknown tutoring student id: {student_id}")
    return str(row["canonical_name"])


def _lesson_id(conn: sqlite3.Connection, student_id: int, lesson_date: str | None) -> int | None:
    if lesson_date is None:
        row = conn.execute(
            """
            SELECT id FROM tutoring_lessons
            WHERE student_id = ?
            ORDER BY lesson_date DESC, id DESC
            LIMIT 1
            """,
            (student_id,),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT id FROM tutoring_lessons
            WHERE student_id = ? AND lesson_date = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (student_id, lesson_date),
        ).fetchone()
    return int(row["id"]) if row is not None else None


def _word_entry_id(conn: sqlite3.Connection, word: str) -> int | None:
    row = conn.execute(
        """
        SELECT id
        FROM tutoring_word_entries
        WHERE lower(canonical_headword) = lower(?)
        UNION
        SELECT word_entry_id AS id
        FROM tutoring_word_aliases
        WHERE lower(alias) = lower(?)
        LIMIT 1
        """,
        (word, word),
    ).fetchone()
    return int(row["id"]) if row is not None else None


def _create_word_entry(conn: sqlite3.Connection, item: StudyItem) -> int:
    cursor = conn.execute(
        "INSERT INTO tutoring_word_entries(canonical_headword) VALUES (?)",
        (item.word,),
    )
    word_id = int(cursor.lastrowid)
    if item.meaning:
        conn.execute(
            "INSERT INTO tutoring_word_senses(word_entry_id, definition) VALUES (?, ?)",
            (word_id, item.meaning),
        )
    return word_id


def _insert_quiz_session(
    conn: sqlite3.Connection,
    student_id: int,
    lesson_id: int | None,
    observed_on: str,
    source_label: str | None,
    matched: list[tuple[StudyItem, int]],
    skipped: list[str],
    score: int,
    total: int,
    pct: float | None,
) -> int:
    payload: dict[str, JsonValue] = {
        "source": "classcard",
        "source_label": source_label,
        "items": [_item_payload(item, word_id) for item, word_id in matched],
        "skipped_words": list(skipped),
    }
    cursor = conn.execute(
        """
        INSERT INTO tutoring_quiz_sessions(
            student_id, lesson_id, quiz_date, subject, score, total, pct, payload_json
        )
        VALUES (?, ?, ?, 'classcard', ?, ?, ?, ?)
        """,
        (student_id, lesson_id, observed_on, score, total, pct, dump_json(payload)),
    )
    return int(cursor.lastrowid)


def _insert_quiz_item(
    conn: sqlite3.Connection,
    quiz_session_id: int,
    word_id: int,
    item: StudyItem,
) -> None:
    payload: dict[str, JsonValue] = {
        "source": "classcard",
        "word": item.word,
        "status": item.status,
        "correct_count": item.correct_count,
        "wrong_count": item.wrong_count,
    }
    conn.execute(
        """
        INSERT OR REPLACE INTO tutoring_quiz_items(
            quiz_session_id, word_entry_id, is_correct, payload_json
        )
        VALUES (?, ?, ?, ?)
        """,
        (quiz_session_id, word_id, 1 if item.is_correct else 0, dump_json(payload)),
    )


def _upsert_word_state(
    conn: sqlite3.Connection,
    student_id: int,
    word_id: int,
    item: StudyItem,
    observed_on: str,
    source_label: str | None,
) -> None:
    row = conn.execute(
        """
        SELECT id, attrs_json FROM tutoring_student_word_state
        WHERE student_id = ? AND word_entry_id = ?
        """,
        (student_id, word_id),
    ).fetchone()
    attrs = load_json(str(row["attrs_json"])) if row is not None else {}
    attrs["classcard_last_status"] = item.status
    attrs["classcard_last_observed_on"] = observed_on
    if source_label:
        attrs["classcard_source_label"] = source_label
    if row is None:
        conn.execute(
            """
            INSERT INTO tutoring_student_word_state(
                student_id, word_entry_id, wrong_count, correct_count, last_seen_at, attrs_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (student_id, word_id, item.wrong_count, item.correct_count, observed_on, dump_json(attrs)),
        )
        return
    conn.execute(
        """
        UPDATE tutoring_student_word_state
        SET wrong_count = wrong_count + ?,
            correct_count = correct_count + ?,
            last_seen_at = ?,
            attrs_json = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (item.wrong_count, item.correct_count, observed_on, dump_json(attrs), int(row["id"])),
    )


def _students(conn: sqlite3.Connection, student: str | None) -> list[sqlite3.Row]:
    if student:
        row = conn.execute(
            """
            SELECT id, canonical_name
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
            SELECT id, canonical_name
            FROM tutoring_students
            WHERE active = 1
            ORDER BY canonical_name
            """,
        ).fetchall(),
    )


def _student_summary(
    conn: sqlite3.Connection,
    student_id: int,
    student_name: str,
    limit: int,
    mastery_threshold: int,
) -> dict[str, JsonValue]:
    rows = _word_rows(conn, student_id)
    words = [_word_state_json(row, mastery_threshold) for row in rows]
    counts = dict.fromkeys(("mastered", "learning", "review", "weak", "new"), 0)
    for word in words:
        counts[str(word["status"])] += 1
    tracked_words = sum(1 for word in words if int(word["attempts"]) > 0)
    attempts = sum(int(word["attempts"]) for word in words)
    correct = sum(int(word["correct_count"]) for word in words)
    weak_words = [word for word in words if word["status"] in {"weak", "review"}]
    weak_words.sort(key=_due_sort_key)
    return {
        "student": student_name,
        "student_id": student_id,
        "total_words": len(words),
        "tracked_words": tracked_words,
        "attempts": attempts,
        "accuracy_pct": round(correct / attempts * 100, 1) if attempts else None,
        "status_counts": counts,
        "trouble_words": weak_words[:limit],
        "recent_sessions": _recent_sessions(conn, student_id, limit),
    }


def _word_rows(conn: sqlite3.Connection, student_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            WITH assigned AS (
                SELECT DISTINCT lw.word_entry_id
                FROM tutoring_lesson_words lw
                JOIN tutoring_lessons l ON l.id = lw.lesson_id
                WHERE l.student_id = ?
            ),
            state_words AS (
                SELECT word_entry_id
                FROM tutoring_student_word_state
                WHERE student_id = ?
            ),
            words AS (
                SELECT word_entry_id FROM assigned
                UNION
                SELECT word_entry_id FROM state_words
            )
            SELECT e.id AS word_entry_id,
                   e.canonical_headword AS headword,
                   ifnull(
                       (
                           SELECT definition
                           FROM tutoring_word_senses
                           WHERE word_entry_id = e.id
                           ORDER BY id
                           LIMIT 1
                       ),
                       ''
                   ) AS meaning,
                   coalesce(s.correct_count, 0) AS correct_count,
                   coalesce(s.wrong_count, 0) AS wrong_count,
                   s.last_seen_at,
                   CASE WHEN a.word_entry_id IS NULL THEN 0 ELSE 1 END AS assigned
            FROM words w
            JOIN tutoring_word_entries e ON e.id = w.word_entry_id
            LEFT JOIN tutoring_student_word_state s
              ON s.student_id = ? AND s.word_entry_id = e.id
            LEFT JOIN assigned a ON a.word_entry_id = e.id
            ORDER BY lower(e.canonical_headword)
            """,
            (student_id, student_id, student_id),
        ).fetchall(),
    )


def _word_state_json(row: sqlite3.Row, mastery_threshold: int) -> dict[str, JsonValue]:
    correct_count = int(row["correct_count"])
    wrong_count = int(row["wrong_count"])
    attempts = correct_count + wrong_count
    accuracy = round(correct_count / attempts * 100, 1) if attempts else None
    status = _mastery_status(correct_count, wrong_count, mastery_threshold)
    return {
        "word_entry_id": int(row["word_entry_id"]),
        "headword": str(row["headword"]),
        "meaning": str(row["meaning"]),
        "status": status,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "attempts": attempts,
        "accuracy_pct": accuracy,
        "last_seen_at": str(row["last_seen_at"]) if row["last_seen_at"] is not None else None,
        "assigned": bool(row["assigned"]),
    }


def _mastery_status(correct_count: int, wrong_count: int, mastery_threshold: int) -> str:
    attempts = correct_count + wrong_count
    if attempts == 0:
        return "new"
    accuracy = correct_count / attempts
    if correct_count >= mastery_threshold and accuracy >= _MASTERY_ACCURACY_THRESHOLD:
        return "mastered"
    if wrong_count >= correct_count:
        return "weak"
    if wrong_count > 0:
        return "review"
    return "learning"


def _recent_sessions(conn: sqlite3.Connection, student_id: int, limit: int) -> list[JsonValue]:
    rows = conn.execute(
        """
        SELECT id, quiz_date, score, total, pct, payload_json
        FROM tutoring_quiz_sessions
        WHERE student_id = ? AND subject = 'classcard'
        ORDER BY quiz_date DESC, id DESC
        LIMIT ?
        """,
        (student_id, limit),
    ).fetchall()
    sessions: list[JsonValue] = []
    for row in rows:
        payload = load_json(str(row["payload_json"]))
        sessions.append(
            {
                "id": int(row["id"]),
                "quiz_date": str(row["quiz_date"]),
                "score": int(row["score"]) if row["score"] is not None else None,
                "total": int(row["total"]) if row["total"] is not None else None,
                "pct": float(row["pct"]) if row["pct"] is not None else None,
                "source_label": payload.get("source_label"),
            },
        )
    return sessions


def _due_sort_key(item: JsonValue) -> tuple[int, int, float, str]:
    if not isinstance(item, dict):
        return (9, 0, 100.0, "")
    status_order = {"weak": 0, "review": 1, "new": 2, "learning": 3, "mastered": 4}
    status = str(item.get("status", ""))
    wrong_count = int(item.get("wrong_count", 0))
    accuracy_raw = item.get("accuracy_pct")
    accuracy = float(accuracy_raw) if isinstance(accuracy_raw, int | float) else 100.0
    return (status_order.get(status, 9), -wrong_count, accuracy, str(item.get("headword", "")))


def _item_payload(item: StudyItem, word_id: int) -> dict[str, JsonValue]:
    return {
        "word": item.word,
        "word_entry_id": word_id,
        "status": item.status,
        "correct_count": item.correct_count,
        "wrong_count": item.wrong_count,
    }
