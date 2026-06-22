from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from chat_lms_agent.daily_lesson_homework_db import (
    connect,
    previous_homework,
    session_records,
    session_subject,
    today_sessions,
)
from chat_lms_agent.daily_lesson_homework_sheet import (
    cell,
    clean,
    date_tab,
    discover_blocks,
    range_a1,
    sheet_rows,
)
from chat_lms_agent.outbound_sync import OutboundItem

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

DEFAULT_SOURCE_KEY = "daily_lesson_homework.2026_06"
A_PLUS_MIN = 95.0
A_MIN = 90.0
B_MIN = 80.0
C_MIN = 70.0


@dataclass(frozen=True, slots=True)
class HomeworkMapping:
    source_key: str
    spreadsheet_id: str
    class_alias_map: dict[str, str]


@dataclass(frozen=True, slots=True)
class StudentItemInput:
    mapping: HomeworkMapping
    tab: str
    lesson_date: str
    db_class: str
    row: int
    record: sqlite3.Row
    current_value: str


@dataclass(frozen=True, slots=True)
class DueHomeworkItemInput:
    mapping: HomeworkMapping
    tab: str
    lesson_date: str
    db_class: str
    footer_row: int
    session_id: int
    previous: sqlite3.Row | None
    subject: str
    current_value: str


def build_daily_lesson_homework_items(
    db_path: str | Path,
    *,
    source_key: str,
    lesson_date: str,
    current_values_payload: dict[str, JsonValue],
    class_codes: tuple[str, ...] = (),
) -> list[OutboundItem]:
    conn = connect(db_path)
    try:
        mapping = load_homework_mapping(conn, source_key)
        rows = sheet_rows(current_values_payload)
        tab = date_tab(lesson_date)
        blocks = discover_blocks(rows, mapping.class_alias_map)
        wanted = set(class_codes)
        sessions = today_sessions(conn, lesson_date, wanted or set(blocks))
        items: list[OutboundItem] = []
        for db_class, session in sessions.items():
            block = blocks.get(db_class)
            if block is None:
                continue
            class_id = int(cast("int | str", session["class_id"]))
            session_id = int(cast("int | str", session["id"]))
            subject = session_subject(
                conn,
                class_id,
                lesson_date,
                clean(cast("object", session["subject"])),
            )
            records = session_records(conn, session_id)
            for record in records:
                student_name = clean(cast("object", record["student_name"]))
                row = block.students.get(student_name)
                if row is None:
                    message = (
                        "student not found in homework sheet block: "
                        f"{db_class} {student_name}"
                    )
                    raise LookupError(message)
                items.append(
                    _student_item(
                        StudentItemInput(
                            mapping,
                            tab,
                            lesson_date,
                            db_class,
                            row,
                            record,
                            cell(rows, row, 9),
                        ),
                    ),
                )
            previous = previous_homework(conn, class_id, lesson_date, subject)
            items.append(
                _due_homework_item(
                    DueHomeworkItemInput(
                        mapping,
                        tab,
                        lesson_date,
                        db_class,
                        block.footer_row,
                        session_id,
                        previous,
                        subject,
                        cell(rows, block.footer_row, 10),
                    ),
                ),
            )
        return items
    finally:
        conn.close()


def load_homework_mapping(conn: sqlite3.Connection, source_key: str) -> HomeworkMapping:
    row = cast(
        "sqlite3.Row | None",
        conn.execute(
            """
        SELECT spreadsheet_id, payload_json
        FROM external_source_mappings
        WHERE source_key = ?
        """,
            (source_key,),
        ).fetchone(),
    )
    if row is None:
        message = f"external mapping not found: {source_key}"
        raise LookupError(message)
    raw_payload = cast("object", json.loads(clean(cast("object", row["payload_json"])) or "{}"))
    if not isinstance(raw_payload, dict):
        message = f"mapping payload must be an object: {source_key}"
        raise TypeError(message)
    payload = cast("dict[str, JsonValue]", raw_payload)
    alias_raw = payload.get("class_alias_map", {})
    aliases = (
        {str(key): str(value) for key, value in alias_raw.items()}
        if isinstance(alias_raw, dict)
        else {}
    )
    spreadsheet_id = _first_string(
        payload.get("spreadsheet_id"),
        cast("object", row["spreadsheet_id"]),
    )
    return HomeworkMapping(
        source_key=source_key,
        spreadsheet_id=spreadsheet_id,
        class_alias_map=aliases,
    )


def _student_item(item: StudentItemInput) -> OutboundItem:
    student_id = int(cast("int | str", item.record["student_id"]))
    session_id = int(cast("int | str", item.record["session_id"]))
    target_cell = range_a1(item.tab, f"I{item.row}")
    return OutboundItem(
        source_key=item.mapping.source_key,
        logical_entity="daily_homework_cell",
        local_ids=(f"session:{session_id}", f"student:{student_id}"),
        target_period=item.lesson_date,
        target_role=f"homework_completion:{item.db_class}:student:{student_id}:I{item.row}",
        schema_version="v1",
        mode="update",
        spreadsheet_id=item.mapping.spreadsheet_id,
        sheet_name=item.tab,
        range_a1=target_cell,
        target_value=_grade(cast("float | str | None", item.record["homework_score"])),
        current_value=item.current_value,
        payload={
            "overwrite_policy": "protect_non_empty",
            "kind": "homework_completion_grade",
            "class_name": item.db_class,
            "student_id": str(student_id),
            "student_name": clean(cast("object", item.record["student_name"])),
            "session_id": str(session_id),
            "homework_score": cast("float | str | None", item.record["homework_score"]),
            "attendance": clean(cast("object", item.record["attendance"])),
            "target_cell": target_cell,
        },
    )


def _due_homework_item(item: DueHomeworkItemInput) -> OutboundItem:
    previous_id = "" if item.previous is None else str(int(cast("int | str", item.previous["id"])))
    target_value = "" if item.previous is None else clean(cast("object", item.previous["homework"]))
    target_cell = range_a1(item.tab, f"J{item.footer_row}")
    return OutboundItem(
        source_key=item.mapping.source_key,
        logical_entity="daily_homework_due_cell",
        local_ids=(f"today_session:{item.session_id}", f"previous_session:{previous_id}"),
        target_period=item.lesson_date,
        target_role=f"due_homework:{item.db_class}:J{item.footer_row}",
        schema_version="v1",
        mode="update",
        spreadsheet_id=item.mapping.spreadsheet_id,
        sheet_name=item.tab,
        range_a1=target_cell,
        target_value=target_value,
        current_value=item.current_value,
        payload={
            "overwrite_policy": "protect_non_empty",
            "kind": "due_homework_content",
            "class_name": item.db_class,
            "today_session_id": str(item.session_id),
            "previous_session_id": previous_id,
            "subject": item.subject,
            "target_cell": target_cell,
        },
    )


def _grade(value: float | str | None) -> str:
    score = 0.0 if value is None else float(value)
    if score >= A_PLUS_MIN:
        return "A+"
    if score >= A_MIN:
        return "A"
    if score >= B_MIN:
        return "B"
    if score >= C_MIN:
        return "C"
    return "D"


def _first_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    message = "required mapping string is missing"
    raise ValueError(message)
