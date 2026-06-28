from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from json import JSONDecodeError
from pathlib import Path

from chat_lms_agent.daily_lesson_homework_db import previous_homework
from chat_lms_agent.outbound_sync import OutboundItem

WEEKDAY_CODES = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
SUBJECT_LABELS = {
    "grammar": "문법",
    "문법": "문법",
    "reading": "독해",
    "독해": "독해",
    "vocabulary": "어휘",
    "어휘": "어휘",
    "listening": "듣기",
    "듣기": "듣기",
    "": "",
}
SEPARATOR = "-------------------"


@dataclass(frozen=True, slots=True)
class JournalRowMapping:
    db_class: str
    sheet_class: str
    row: int


@dataclass(frozen=True, slots=True)
class JournalMapping:
    source_key: str
    spreadsheet_id: str
    sheet_name: str
    class_rows: dict[str, JournalRowMapping]
    date_columns: dict[str, str]


def build_daily_management_journal_items(
    db_path: str | Path,
    *,
    source_key: str,
    start_date: str,
    end_date: str,
    current_values: dict[str, str],
    include_label_items: bool = True,
) -> list[OutboundItem]:
    """Build deterministic, overwrite-protected journal cell items from the local DB.

    The function reads only mapping metadata and lesson records. It does not call
    Google APIs and does not write external sheets.
    """

    conn = _connect(db_path)
    try:
        mapping = _load_mapping(conn, source_key)
        rows = _session_rows(conn, start_date, end_date, tuple(mapping.class_rows))
        items: list[OutboundItem] = []
        if include_label_items:
            items.extend(_label_items(mapping, current_values, start_date[:7]))
        for row in rows:
            class_code = _clean(row["class_code"])
            row_mapping = mapping.class_rows.get(class_code)
            if row_mapping is None:
                continue
            session_date = _clean(row["session_date"])
            column = mapping.date_columns.get(session_date)
            if column is None:
                continue
            cell = f"{column}{row_mapping.row}"
            range_a1 = _range_a1(mapping.sheet_name, cell)
            target_value = _render_journal_cell(conn, row, row_mapping)
            items.append(
                OutboundItem(
                    source_key=source_key,
                    logical_entity="lesson_journal_cell",
                    local_ids=(
                        f"session:{int(row['id'])}",
                        f"class:{int(row['class_id'])}",
                        f"range:{cell}",
                    ),
                    target_period=start_date[:7],
                    target_role="journal_cell",
                    schema_version="v1",
                    mode="update",
                    spreadsheet_id=mapping.spreadsheet_id,
                    sheet_name=mapping.sheet_name,
                    range_a1=range_a1,
                    target_value=target_value,
                    current_value=current_values.get(cell, ""),
                    payload={
                        "overwrite_policy": "protect_non_empty",
                        "renderer": "daily_management_journal_v1",
                        "session_id": int(row["id"]),
                        "class_id": int(row["class_id"]),
                        "db_class": class_code,
                        "sheet_class": row_mapping.sheet_class,
                        "cell": cell,
                    },
                ),
            )
        return items
    finally:
        conn.close()


def current_values_from_json(payload: object) -> dict[str, str]:
    """Convert a bounded Sheets values response or cell map into A1-cell values."""

    if not isinstance(payload, dict):
        message = "current values payload must be an object"
        raise TypeError(message)
    # Transparently unwrap the CLI's stdout envelope {"status","result","out"} so
    # `gws sheets values-get` output can feed `journal-plan --current-values-json`
    # directly; the raw Sheets response lives under "result".
    envelope = payload.get("result")
    if "status" in payload and isinstance(envelope, dict):
        payload = envelope
    cell_values = payload.get("cell_values")
    if isinstance(cell_values, dict):
        return {str(key): _clean(value) for key, value in cell_values.items()}
    if _looks_like_cell_map(payload):
        return {str(key): _clean(value) for key, value in payload.items()}
    values = payload.get("values")
    range_name = payload.get("range")
    if not isinstance(values, list) or not isinstance(range_name, str):
        message = "current values must be a cell map or a Sheets values response"
        raise ValueError(message)
    start_col, start_row = _range_start(range_name)
    result: dict[str, str] = {}
    for row_offset, row_values in enumerate(values):
        if not isinstance(row_values, list):
            continue
        for col_offset, value in enumerate(row_values):
            cell = f"{_column_name(start_col + col_offset)}{start_row + row_offset}"
            result[cell] = _clean(value)
    return result


def load_current_values(path: str | Path) -> dict[str, str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return current_values_from_json(payload)


def load_journal_mapping(db_path: str | Path, source_key: str) -> JournalMapping:
    """Load the journal cell mapping (spreadsheet id, tab, rows, columns) from the DB."""
    conn = _connect(db_path)
    try:
        return _load_mapping(conn, source_key)
    finally:
        conn.close()


def journal_read_range(mapping: JournalMapping) -> str:
    """Bounded A1 range covering every cell the journal mapping may write.

    Covers the label column ``B`` plus all mapped date columns, from row 1 to the
    last mapped class row, so the one-shot sync can fetch current values itself.
    """
    max_row = max(row.row for row in mapping.class_rows.values())
    columns = ("B", *mapping.date_columns.values())
    last_column = _column_name(max(_column_index(column) for column in columns))
    return _range_a1(mapping.sheet_name, f"A1:{last_column}{max_row}")


def _load_mapping(conn: sqlite3.Connection, source_key: str) -> JournalMapping:
    row = conn.execute(
        """
        SELECT spreadsheet_id, sheet_name, payload_json
        FROM external_source_mappings
        WHERE source_key = ?
        """,
        (source_key,),
    ).fetchone()
    if row is None:
        message = f"external mapping not found: {source_key}"
        raise LookupError(message)
    try:
        payload = json.loads(_clean(row["payload_json"]) or "{}")
    except JSONDecodeError as error:
        message = f"external mapping payload is invalid JSON: {source_key}"
        raise ValueError(message) from error
    if not isinstance(payload, dict):
        message = f"external mapping payload must be an object: {source_key}"
        raise TypeError(message)
    journal = payload.get("journal_cell_mapping")
    if not isinstance(journal, dict):
        message = f"journal_cell_mapping missing: {source_key}"
        raise ValueError(message)
    spreadsheet_id = _first_string(journal.get("spreadsheet_id"), row["spreadsheet_id"])
    sheet_name = _first_string(journal.get("tab_title"), journal.get("sheet_name"), row["sheet_name"])
    class_rows = _class_rows(journal)
    date_columns = _date_columns(journal)
    return JournalMapping(
        source_key=source_key,
        spreadsheet_id=spreadsheet_id,
        sheet_name=sheet_name,
        class_rows=class_rows,
        date_columns=date_columns,
    )


def _class_rows(journal: dict[object, object]) -> dict[str, JournalRowMapping]:
    teacher_block = journal.get("teacher_block")
    mapped_rows: object = None
    if isinstance(teacher_block, dict):
        mapped_rows = teacher_block.get("mapped_rows")
    if mapped_rows is None:
        mapped_rows = journal.get("class_rows")
    if not isinstance(mapped_rows, dict):
        message = "journal mapping needs teacher_block.mapped_rows"
        raise ValueError(message)
    result: dict[str, JournalRowMapping] = {}
    for db_class, raw in mapped_rows.items():
        if not isinstance(db_class, str) or not isinstance(raw, dict):
            continue
        row_value = raw.get("row")
        sheet_class = raw.get("sheet_class", db_class)
        if not isinstance(row_value, int) or not isinstance(sheet_class, str):
            continue
        result[db_class] = JournalRowMapping(
            db_class=db_class,
            sheet_class=sheet_class,
            row=row_value,
        )
    if not result:
        message = "journal mapping has no usable class rows"
        raise ValueError(message)
    return result


def _date_columns(journal: dict[object, object]) -> dict[str, str]:
    raw = journal.get("date_column_map")
    if raw is None:
        raw = journal.get("date_columns")
    if not isinstance(raw, dict):
        message = "journal mapping needs date_column_map"
        raise ValueError(message)
    result = {str(key): str(value).upper() for key, value in raw.items() if isinstance(value, str)}
    if not result:
        message = "journal mapping has no usable date columns"
        raise ValueError(message)
    invalid = {key: value for key, value in result.items() if not re.fullmatch(r"[A-Z]+", value)}
    if invalid:
        message = f"journal mapping has invalid date columns: {invalid}"
        raise ValueError(message)
    return result


def _label_items(
    mapping: JournalMapping,
    current_values: dict[str, str],
    target_period: str,
) -> list[OutboundItem]:
    items: list[OutboundItem] = []
    for row_mapping in mapping.class_rows.values():
        cell = f"B{row_mapping.row}"
        items.append(
            OutboundItem(
                source_key=mapping.source_key,
                logical_entity="journal_class_label",
                local_ids=(f"class:{row_mapping.db_class}", f"range:{cell}"),
                target_period=target_period,
                target_role="class_label",
                schema_version="v1",
                mode="update",
                spreadsheet_id=mapping.spreadsheet_id,
                sheet_name=mapping.sheet_name,
                range_a1=_range_a1(mapping.sheet_name, cell),
                target_value=row_mapping.sheet_class,
                current_value=current_values.get(cell, ""),
                payload={
                    "overwrite_policy": "protect_non_empty",
                    "renderer": "daily_management_journal_label_v1",
                    "db_class": row_mapping.db_class,
                    "sheet_class": row_mapping.sheet_class,
                    "cell": cell,
                },
            ),
        )
    return items


def _session_rows(
    conn: sqlite3.Connection,
    start_date: str,
    end_date: str,
    class_codes: tuple[str, ...],
) -> tuple[sqlite3.Row, ...]:
    placeholders = ", ".join("?" for _ in class_codes)
    rows = conn.execute(
        f"""
        SELECT
            s.id,
            s.class_id,
            c.code AS class_code,
            c.canonical_name,
            s.session_date,
            s.subject,
            s.progress,
            s.homework,
            s.payload_json
        FROM sessions s
        JOIN classes c ON c.id = s.class_id
        WHERE s.session_kind = 'main'
          AND s.session_date BETWEEN ? AND ?
          AND c.code IN ({placeholders})
        ORDER BY s.session_date, c.code, s.id
        """,
        (start_date, end_date, *class_codes),
    ).fetchall()
    return tuple(rows)


def _render_journal_cell(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    row_mapping: JournalRowMapping,
) -> str:
    """Render the parent-facing journal cell: 과제 및 테스트 / 수업 / 과제 및 테스트.

    Block 1 (today): today's vocabulary + listening curriculum, plus the homework
    that was due today (the previous same-subject session's homework, with its
    assign~due date range). Block 2 (수업): the subject + textbook header and the
    *actual* progress taught — never the planned chapter. Block 3 (next class day):
    that day's vocabulary + listening, plus today's newly assigned homework with its
    today~due date range. The class label lives in the sheet's own column, so the
    cell text carries no class-name line.
    """
    _ = row_mapping
    session_date = date.fromisoformat(_clean(row["session_date"]))
    class_id = int(row["class_id"])
    subject = _clean(row["subject"]) or _scheduled_subject(conn, class_id, session_date)
    today_curriculum = _curriculum_by_subject(conn, class_id, session_date)

    block1 = [
        f"{_date_label(session_date)} 과제 및 테스트",
        *_vocab_lines(_vocabulary(today_curriculum)),
        _listening_line(_listening(today_curriculum)),
    ]
    due_today = previous_homework(conn, class_id, session_date.isoformat(), subject)
    if due_today is not None:
        assigned = date.fromisoformat(_clean(due_today["session_date"]))
        block1.append(
            f"H) {_clean(due_today['homework'])} "
            f"({_date_label(assigned)}~{_date_label(session_date)})",
        )

    textbook = _actual_textbook(row["payload_json"]) or _curriculum_textbook(
        today_curriculum,
        subject,
    )
    progress = _required_session_field(row, "progress")
    block2 = [
        f"{_date_label(session_date)} 수업",
        f"({_subject_label(subject)}) {textbook}".rstrip(),
        f"1. {progress}",
    ]

    parts = [*block1, SEPARATOR, *block2]
    next_day = _next_active_day(conn, class_id, session_date)
    if next_day is not None:
        next_curriculum = _curriculum_by_subject(conn, class_id, next_day)
        due_day = _next_same_subject_day(conn, class_id, session_date, subject) or next_day
        homework = _required_session_field(row, "homework")
        parts.extend(
            [
                SEPARATOR,
                f"{_date_label(next_day)} 과제 및 테스트",
                *_vocab_lines(_vocabulary(next_curriculum)),
                _listening_line(_listening(next_curriculum)),
                f"H) {homework} ({_date_label(session_date)}~{_date_label(due_day)})",
            ],
        )
    return "\n".join(parts)


def _required_session_field(row: sqlite3.Row, field: str) -> str:
    value = _clean(row[field])
    if value:
        return value
    if field == "homework" and _homework_intentionally_blank(row["payload_json"]):
        return ""
    message = (
        "daily management journal outbound blocked missing "
        f"{field}: session_id={int(row['id'])} "
        f"class={_clean(row['class_code'])} "
        f"date={_clean(row['session_date'])}"
    )
    raise ValueError(message)


def _homework_intentionally_blank(payload_json: object) -> bool:
    if not isinstance(payload_json, str) or not payload_json:
        return False
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    value = payload.get("homework_intentionally_blank")
    return value is True


def _vocabulary(curriculum: dict[str, str]) -> str:
    return curriculum.get("vocabulary") or curriculum.get("어휘") or ""


def _listening(curriculum: dict[str, str]) -> str:
    return curriculum.get("listening") or curriculum.get("듣기") or ""


def _vocab_lines(content: str) -> list[str]:
    lines = content.split("\n") if content else []
    if not lines or not lines[0]:
        return ["1. X"]
    return [f"1. {lines[0]}", *lines[1:]]


def _listening_line(content: str) -> str:
    return f"2. {content}" if content else "2. X"


def _curriculum_textbook(curriculum: dict[str, str], subject: str) -> str:
    """First line (textbook name) of today's main-subject curriculum entry."""
    label = _subject_label(subject)
    for key in (_clean(subject).lower(), label.lower()):
        content = curriculum.get(key)
        if content:
            return content.split("\n", 1)[0]
    return ""


def _actual_textbook(payload_json: object) -> str:
    if not isinstance(payload_json, str) or not payload_json:
        return ""
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return ""
    if isinstance(payload, dict):
        value = payload.get("actual_textbook")
        if isinstance(value, str):
            return value.strip()
    return ""


def _next_same_subject_day(
    conn: sqlite3.Connection,
    class_id: int,
    lesson_date: date,
    subject: str,
) -> date | None:
    target = _subject_label(subject)
    candidate = lesson_date + timedelta(days=1)
    for _ in range(120):
        scheduled = _scheduled_subject(conn, class_id, candidate)
        if scheduled and _subject_label(scheduled) == target:
            return candidate
        candidate += timedelta(days=1)
    return None


def _curriculum_by_subject(
    conn: sqlite3.Connection,
    class_id: int,
    planned_on: date,
) -> dict[str, str]:
    rows = conn.execute(
        """
        SELECT subject, content
        FROM curriculum_entries
        WHERE class_id = ? AND planned_on = ?
        ORDER BY id
        """,
        (class_id, planned_on.isoformat()),
    ).fetchall()
    result: dict[str, str] = {}
    for row in rows:
        result.setdefault(_clean(row["subject"]).lower(), _clean(row["content"]))
    return result


def _scheduled_subject(conn: sqlite3.Connection, class_id: int, lesson_date: date) -> str:
    if not _table_exists(conn, "class_schedule_entries"):
        return ""
    weekday = WEEKDAY_CODES[lesson_date.weekday()]
    row = conn.execute(
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
    ).fetchone()
    return _clean(row["subject"]) if row is not None else ""


def _next_active_day(conn: sqlite3.Connection, class_id: int, lesson_date: date) -> date | None:
    if not _table_exists(conn, "class_schedule_entries"):
        return None
    candidate = lesson_date + timedelta(days=1)
    for _ in range(120):
        if _active_on(conn, class_id, candidate):
            return candidate
        candidate += timedelta(days=1)
    return None


def _active_on(conn: sqlite3.Connection, class_id: int, lesson_date: date) -> bool:
    weekday = WEEKDAY_CODES[lesson_date.weekday()]
    exception_clause = ""
    params: list[object] = [class_id, weekday]
    if _table_exists(conn, "class_schedule_exceptions"):
        exception_clause = """
          AND NOT EXISTS (
            SELECT 1
            FROM class_schedule_exceptions ex
            WHERE ex.class_id = se.class_id
              AND ex.exception_date = ?
              AND ex.status = 'cancelled'
          )
        """
        params.append(lesson_date.isoformat())
    row = conn.execute(
        f"""
        SELECT 1
        FROM class_schedule_entries se
        WHERE se.class_id = ?
          AND se.weekday = ?
          AND se.session_kind = 'main'
          AND se.status = 'active'
          {exception_clause}
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    return row is not None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _range_start(range_name: str) -> tuple[int, int]:
    cell_part = range_name.split("!", 1)[-1].split(":", 1)[0]
    match = re.search(r"([A-Z]+)([0-9]+)$", cell_part, flags=re.IGNORECASE)
    if match is None:
        message = f"cannot parse range start: {range_name}"
        raise ValueError(message)
    return (_column_index(match.group(1)), int(match.group(2)))


def _column_index(column: str) -> int:
    value = 0
    for char in column.upper():
        value = value * 26 + ord(char) - 64
    return value


def _column_name(index: int) -> str:
    value = ""
    while index:
        index, rem = divmod(index - 1, 26)
        value = chr(65 + rem) + value
    return value


def _looks_like_cell_map(payload: dict[object, object]) -> bool:
    if not payload:
        return False
    return all(isinstance(key, str) and re.fullmatch(r"[A-Z]+[0-9]+", key) for key in payload)


def _range_a1(sheet_name: str, cell: str) -> str:
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'!{cell}"


def _subject_label(value: str) -> str:
    cleaned = _clean(value)
    return SUBJECT_LABELS.get(cleaned.lower(), SUBJECT_LABELS.get(cleaned, cleaned))


def _date_label(value: date) -> str:
    return f"{value.month}/{value.day}"


def _first_string(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    message = "required string mapping field is missing"
    raise ValueError(message)


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn
