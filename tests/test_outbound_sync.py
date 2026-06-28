from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, cast

import pytest

from chat_lms_agent import daily_lesson_homework_handlers, outbound_handlers
from chat_lms_agent.commands import main
from chat_lms_agent.daily_lesson_homework_outbound import (
    build_daily_lesson_homework_items,
)
from chat_lms_agent.daily_management_outbound import (
    build_daily_management_journal_items,
    current_values_from_json,
)
from chat_lms_agent.outbound_sync import (
    OutboundItem,
    build_plan,
    content_hash,
    ensure_outbound_ledger,
    idempotency_key,
    normalize_for_hash,
    record_outbound_result,
)

if TYPE_CHECKING:
    from pathlib import Path

EXPECTED_JOURNAL_KEY = (
    "daily_management.2026_06|session_journal|class:EBSS,session:42|"
    "2026-06|append_row|v1"
)


def _create_single_student_daily_homework_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "chat_lms.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE classes(
          id INTEGER PRIMARY KEY,
          code TEXT NOT NULL,
          canonical_name TEXT NOT NULL
        );
        CREATE TABLE students(
          id INTEGER PRIMARY KEY,
          canonical_name TEXT NOT NULL,
          attrs_json TEXT NOT NULL DEFAULT '{}',
          active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE sessions(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          session_kind TEXT NOT NULL,
          session_date TEXT NOT NULL,
          subject TEXT,
          progress TEXT,
          homework TEXT,
          payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE student_session_records(
          id INTEGER PRIMARY KEY,
          session_id INTEGER NOT NULL,
          student_id INTEGER NOT NULL,
          attendance TEXT,
          homework_score REAL,
          note TEXT,
          payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE class_schedule_entries(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          weekday TEXT NOT NULL,
          session_kind TEXT,
          subject TEXT,
          status TEXT NOT NULL
        );
        CREATE TABLE external_source_mappings(
          source_key TEXT PRIMARY KEY,
          spreadsheet_id TEXT,
          sheet_name TEXT,
          payload_json TEXT NOT NULL
        );
        """,
    )
    conn.execute("INSERT INTO classes VALUES (2, 'EISS', 'EISS')")
    conn.execute("INSERT INTO students(id, canonical_name) VALUES (6, 'Ben')")
    conn.execute(
        """
        INSERT INTO sessions
        VALUES (579, 2, 'main', '2026-06-15', 'grammar', '', 'essay test', '{}')
        """,
    )
    conn.execute(
        """
        INSERT INTO sessions
        VALUES (592, 2, 'main', '2026-06-22', 'grammar', '', '', '{}')
        """,
    )
    conn.execute(
        """
        INSERT INTO student_session_records(session_id, student_id, attendance, homework_score)
        VALUES (592, 6, 'present', 100)
        """,
    )
    conn.execute(
        """
        INSERT INTO external_source_mappings
        VALUES ('daily_lesson_homework.2026_06', 'sheet-1', '1', ?)
        """,
        (json.dumps({"spreadsheet_id": "sheet-1", "class_alias_map": {"EISS": "EISS"}}),),
    )
    conn.commit()
    conn.close()
    return db_path


def test_idempotency_key_is_stable_and_namespaced() -> None:
    key = idempotency_key(
        source_key="daily_management.2026_06",
        logical_entity="session_journal",
        local_ids=["session:42", "class:EBSS"],
        target_period="2026-06",
        target_role="append_row",
        schema_version="v1",
    )

    assert key == EXPECTED_JOURNAL_KEY


def test_normalized_hash_collapses_whitespace_and_key_order() -> None:
    left = normalize_for_hash({"b": "  EBSS  ", "a": ["Student   Book", {"x": None}]})
    right = normalize_for_hash({"a": ["Student Book", {"x": ""}], "b": "EBSS"})

    assert left == right


def test_existing_cell_plan_skips_unchanged_and_updates_diff(tmp_path: Path) -> None:
    db_path = tmp_path / "chat_lms.db"
    ensure_outbound_ledger(db_path)
    unchanged = OutboundItem(
        source_key="daily_lesson_homework.2026_06",
        logical_entity="homework_grade",
        local_ids=("session:1", "student:1"),
        target_period="2026-06-19",
        target_role="I7",
        schema_version="v1",
        mode="update",
        spreadsheet_id="sheet-1",
        sheet_name="19",
        range_a1="'19'!I7",
        target_value="A+",
        current_value="A+",
        payload={"score": 100},
    )
    changed = OutboundItem(
        source_key="daily_lesson_homework.2026_06",
        logical_entity="homework_grade",
        local_ids=("session:1", "student:2"),
        target_period="2026-06-19",
        target_role="I8",
        schema_version="v1",
        mode="update",
        spreadsheet_id="sheet-1",
        sheet_name="19",
        range_a1="'19'!I8",
        target_value="D",
        current_value="F",
        payload={"score": 0},
    )

    plan = build_plan(db_path, [unchanged, changed])

    assert plan["summary"] == {
        "total": 2,
        "skip_current_matches": 1,
        "write_changed": 1,
    }
    assert [item["decision"] for item in plan["items"]] == ["skip_current_matches", "write_changed"]
    assert plan["write_payload"]["data"] == [{"range": "'19'!I8", "values": [["D"]]}]


def test_protected_existing_cell_flags_human_edit_conflict(tmp_path: Path) -> None:
    db_path = tmp_path / "chat_lms.db"
    ensure_outbound_ledger(db_path)
    item = OutboundItem(
        source_key="daily_management.2026_06",
        logical_entity="lesson_journal_cell",
        local_ids=("session:42", "class:EBSS", "range:C2"),
        target_period="2026-06",
        target_role="journal_cell",
        schema_version="v1",
        mode="update",
        spreadsheet_id="sheet-1",
        sheet_name="2026년 6월",
        range_a1="'2026년 6월'!C2",
        target_value="rendered outbound text",
        current_value="manual teacher edit",
        payload={"overwrite_policy": "protect_non_empty"},
    )

    plan = build_plan(db_path, [item])

    assert plan["summary"] == {"total": 1, "review_conflict": 1}
    assert plan["items"][0]["decision"] == "review_conflict"
    assert plan["write_payload"]["data"] == []


def test_protected_existing_cell_allows_outbound_owned_update(tmp_path: Path) -> None:
    db_path = tmp_path / "chat_lms.db"
    old_item = OutboundItem(
        source_key="daily_management.2026_06",
        logical_entity="lesson_journal_cell",
        local_ids=("session:42", "class:EBSS", "range:C2"),
        target_period="2026-06",
        target_role="journal_cell",
        schema_version="v1",
        mode="update",
        spreadsheet_id="sheet-1",
        sheet_name="2026년 6월",
        range_a1="'2026년 6월'!C2",
        target_value="old outbound text",
        current_value="",
        payload={"overwrite_policy": "protect_non_empty"},
    )
    record_outbound_result(
        db_path,
        old_item,
        status="verified",
        external_row_hash=old_item.content_hash,
    )
    new_item = OutboundItem(
        source_key=old_item.source_key,
        logical_entity=old_item.logical_entity,
        local_ids=old_item.local_ids,
        target_period=old_item.target_period,
        target_role=old_item.target_role,
        schema_version=old_item.schema_version,
        mode=old_item.mode,
        spreadsheet_id=old_item.spreadsheet_id,
        sheet_name=old_item.sheet_name,
        range_a1=old_item.range_a1,
        target_value="new outbound text",
        current_value="old outbound text",
        payload=old_item.payload,
    )

    plan = build_plan(db_path, [new_item])

    assert plan["summary"] == {"total": 1, "write_changed": 1}
    assert plan["items"][0]["current_hash"] == content_hash("old outbound text")
    assert plan["write_payload"]["data"] == [
        {"range": "'2026년 6월'!C2", "values": [["new outbound text"]]},
    ]


def test_append_plan_skips_recorded_hash_and_flags_conflict(tmp_path: Path) -> None:
    db_path = tmp_path / "chat_lms.db"
    ensure_outbound_ledger(db_path)
    written = OutboundItem(
        source_key="daily_management.2026_06",
        logical_entity="session_journal",
        local_ids=("session:42",),
        target_period="2026-06",
        target_role="append_row",
        schema_version="v1",
        mode="append",
        spreadsheet_id="sheet-1",
        sheet_name="2026년 6월",
        range_a1="'2026년 6월'!A40:K40",
        target_value=["2026-06-19", "EBSS", "done"],
        current_value=None,
        payload={"session_id": 42, "text": "done"},
    )
    record_outbound_result(
        db_path,
        written,
        status="written",
        external_row_hash=written.content_hash,
    )
    same = written
    changed = OutboundItem(
        source_key=written.source_key,
        logical_entity=written.logical_entity,
        local_ids=written.local_ids,
        target_period=written.target_period,
        target_role=written.target_role,
        schema_version=written.schema_version,
        mode="append",
        spreadsheet_id=written.spreadsheet_id,
        sheet_name=written.sheet_name,
        range_a1=written.range_a1,
        target_value=["2026-06-19", "EBSS", "changed"],
        current_value=None,
        payload={"session_id": 42, "text": "changed"},
    )

    plan = build_plan(db_path, [same, changed])

    assert [item["decision"] for item in plan["items"]] == ["skip_same", "review_conflict"]
    assert plan["write_payload"]["rows"] == []


def test_ledger_unique_key_updates_existing_record(tmp_path: Path) -> None:
    db_path = tmp_path / "chat_lms.db"
    item = OutboundItem(
        source_key="consultation_polished.2026_06",
        logical_entity="consultation",
        local_ids=("draft:abc", "student:1"),
        target_period="2026-06",
        target_role="append_row",
        schema_version="v1",
        mode="append",
        spreadsheet_id="sheet-2",
        sheet_name="6월",
        range_a1="'6월'!A7:K7",
        target_value=["student", "memo"],
        current_value=None,
        payload={"draft_id": "abc"},
    )

    record_outbound_result(db_path, item, status="written", external_row_hash=item.content_hash)
    record_outbound_result(db_path, item, status="verified", external_row_hash=item.content_hash)

    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "select source_key, idempotency_key, status from external_outbound_ledger",
    ).fetchall()
    conn.close()
    assert rows == [(item.source_key, item.idempotency_key, "verified")]


def test_outbound_plan_cli_returns_decisions(tmp_path: Path) -> None:
    db_path = tmp_path / "chat_lms.db"
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "source_key": "daily_lesson_homework.2026_06",
                        "logical_entity": "homework_grade",
                        "local_ids": ["session:1", "student:1"],
                        "target_period": "2026-06-19",
                        "target_role": "I7",
                        "schema_version": "v1",
                        "mode": "update",
                        "spreadsheet_id": "sheet-1",
                        "sheet_name": "19",
                        "range_a1": "'19'!I7",
                        "target_value": "A+",
                        "current_value": "A+",
                        "payload": {"score": 100},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    result = main(
        [
            "outbound",
            "plan",
            "--db",
            str(db_path),
            "--from-json",
            str(plan_path),
            "--json",
        ],
    )

    assert result == 0


def test_daily_management_journal_items_are_deterministic_cells(tmp_path: Path) -> None:
    db_path = tmp_path / "chat_lms.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE classes(
          id INTEGER PRIMARY KEY,
          code TEXT NOT NULL,
          canonical_name TEXT NOT NULL
        );
        CREATE TABLE sessions(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          session_kind TEXT NOT NULL,
          session_date TEXT NOT NULL,
          subject TEXT,
          progress TEXT,
          homework TEXT,
          payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE curriculum_entries(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          planned_on TEXT NOT NULL,
          subject TEXT NOT NULL,
          content TEXT NOT NULL
        );
        CREATE TABLE class_schedule_entries(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          weekday TEXT NOT NULL,
          session_kind TEXT NOT NULL,
          subject TEXT,
          status TEXT NOT NULL
        );
        CREATE TABLE class_schedule_exceptions(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          exception_date TEXT NOT NULL,
          status TEXT NOT NULL
        );
        CREATE TABLE test_results(
          id INTEGER PRIMARY KEY,
          student_id INTEGER NOT NULL,
          session_id INTEGER,
          test_id INTEGER NOT NULL,
          correct INTEGER NOT NULL,
          total INTEGER NOT NULL,
          pct REAL NOT NULL,
          raw_score TEXT NOT NULL,
          attempt_label TEXT,
          payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE tests(
          id INTEGER PRIMARY KEY,
          name TEXT NOT NULL,
          kind TEXT NOT NULL,
          attrs_json TEXT NOT NULL DEFAULT '{}',
          active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE external_source_mappings(
          source_key TEXT PRIMARY KEY,
          spreadsheet_id TEXT,
          sheet_name TEXT,
          payload_json TEXT NOT NULL
        );
        """,
    )
    mapping_payload = {
        "journal_cell_mapping": {
            "spreadsheet_id": "sheet-1",
            "tab_title": "2026년 6월",
            "teacher_block": {
                "mapped_rows": {
                    "EBSS": {"sheet_class": "EBSS", "row": 2},
                },
            },
            "date_column_map": {
                "2026-06-01": "C",
                "2026-06-05": "G",
            },
        },
    }
    conn.execute("INSERT INTO classes VALUES (45, 'EBSS', 'EBSS')")
    conn.execute(
        """
        INSERT INTO sessions(id, class_id, session_kind, session_date, subject, progress, homework)
        VALUES (559, 45, 'main', '2026-06-01', 'reading', 'Unit 1 읽기', 'Student Book p.9')
        """,
    )
    conn.execute(
        """
        INSERT INTO curriculum_entries(class_id, planned_on, subject, content)
        VALUES (45, '2026-06-01', 'vocabulary', 'LV.1 Synthetic Unit 1')
        """,
    )
    conn.execute(
        """
        INSERT INTO class_schedule_entries(class_id, weekday, session_kind, subject, status)
        VALUES (45, 'FR', 'main', 'reading', 'active')
        """,
    )
    conn.execute(
        """
        INSERT INTO external_source_mappings(source_key, spreadsheet_id, sheet_name, payload_json)
        VALUES ('daily_management.2026_06', 'sheet-1', '2026년 6월', ?)
        """,
        (json.dumps(mapping_payload, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()

    items = build_daily_management_journal_items(
        db_path,
        source_key="daily_management.2026_06",
        start_date="2026-06-01",
        end_date="2026-06-30",
        current_values={"C2": ""},
        include_label_items=False,
    )

    assert len(items) == 1
    item = items[0]
    assert item.range_a1 == "'2026년 6월'!C2"
    assert item.local_ids == ("session:559", "class:45", "range:C2")
    assert item.payload["overwrite_policy"] == "protect_non_empty"
    assert item.target_value.startswith("6/1 과제 및 테스트\n1. LV.1 Synthetic Unit 1\n2. X")

    current_values_path = tmp_path / "current_values.json"
    current_values_path.write_text(
        json.dumps({"cell_values": {"B2": "", "C2": ""}}, ensure_ascii=False),
        encoding="utf-8",
    )
    out_dir = tmp_path / "outbound"
    result = main(
        [
            "outbound",
            "daily-management",
            "journal-plan",
            "--database",
            str(db_path),
            "--from",
            "2026-06-01",
            "--to",
            "2026-06-30",
            "--current-values-json",
            str(current_values_path),
            "--out-dir",
            str(out_dir),
            "--json",
        ],
    )

    assert result == 0
    payload = json.loads((out_dir / "batch_update_payload.json").read_text(encoding="utf-8"))
    assert [entry["range"] for entry in payload["data"]] == [
        "'2026년 6월'!B2",
        "'2026년 6월'!C2",
    ]

    result = main(
        [
            "outbound",
            "ledger",
            "record",
            "--database",
            str(db_path),
            "--from-json",
            str(out_dir / "write_items.json"),
            "--status",
            "verified",
            "--json",
        ],
    )

    assert result == 0
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT count(*) FROM external_outbound_ledger").fetchone()[0]
    conn.close()
    assert count == 2


def test_daily_management_journal_blocks_missing_progress_before_outbound(
    tmp_path: Path,
) -> None:
    db_path = _create_daily_management_journal_guard_db(
        tmp_path,
        progress="",
        homework="Workbook p.1",
    )

    with pytest.raises(ValueError, match="blocked missing progress") as error_info:
        build_daily_management_journal_items(
            db_path,
            source_key="daily_management.2026_06",
            start_date="2026-06-24",
            end_date="2026-06-24",
            current_values={"Z4": ""},
            include_label_items=False,
        )

    message = str(error_info.value)
    assert "blocked missing progress" in message
    assert "session_id=596" in message
    assert "class=EISS" in message


def test_daily_management_journal_blocks_missing_homework_before_outbound(
    tmp_path: Path,
) -> None:
    db_path = _create_daily_management_journal_guard_db(tmp_path, progress="Unit 10", homework="")

    with pytest.raises(ValueError, match="blocked missing homework") as error_info:
        build_daily_management_journal_items(
            db_path,
            source_key="daily_management.2026_06",
            start_date="2026-06-24",
            end_date="2026-06-24",
            current_values={"Z4": ""},
            include_label_items=False,
        )

    message = str(error_info.value)
    assert "blocked missing homework" in message
    assert "session_id=596" in message
    assert "class=EISS" in message


def test_daily_management_journal_allows_intentionally_blank_homework(
    tmp_path: Path,
) -> None:
    db_path = _create_daily_management_journal_guard_db(
        tmp_path,
        progress="Unit 10",
        homework="",
        payload_json=json.dumps({"homework_intentionally_blank": True}),
    )

    items = build_daily_management_journal_items(
        db_path,
        source_key="daily_management.2026_06",
        start_date="2026-06-24",
        end_date="2026-06-24",
        current_values={"Z4": ""},
        include_label_items=False,
    )

    assert len(items) == 1
    assert "1. Unit 10" in str(items[0].target_value)


def test_daily_management_journal_rejects_invalid_date_column_mapping(
    tmp_path: Path,
) -> None:
    db_path = _create_daily_management_journal_guard_db(
        tmp_path,
        progress="Unit 10",
        homework="Workbook p.1",
    )
    conn = sqlite3.connect(db_path)
    raw_payload = conn.execute(
        "SELECT payload_json FROM external_source_mappings WHERE source_key = ?",
        ("daily_management.2026_06",),
    ).fetchone()[0]
    payload = json.loads(raw_payload)
    payload["journal_cell_mapping"]["date_column_map"]["2026-06-24"] = "\\"
    conn.execute(
        "UPDATE external_source_mappings SET payload_json = ? WHERE source_key = ?",
        (json.dumps(payload), "daily_management.2026_06"),
    )
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="invalid date columns"):
        build_daily_management_journal_items(
            db_path,
            source_key="daily_management.2026_06",
            start_date="2026-06-24",
            end_date="2026-06-24",
            current_values={"Z4": ""},
            include_label_items=False,
        )


def _create_daily_management_journal_guard_db(
    tmp_path: Path,
    *,
    progress: str,
    homework: str,
    payload_json: str = "{}",
) -> Path:
    db_path = tmp_path / "chat_lms.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE classes(
          id INTEGER PRIMARY KEY,
          code TEXT NOT NULL,
          canonical_name TEXT NOT NULL
        );
        CREATE TABLE sessions(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          session_kind TEXT NOT NULL,
          session_date TEXT NOT NULL,
          subject TEXT,
          progress TEXT,
          homework TEXT,
          payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE curriculum_entries(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          planned_on TEXT NOT NULL,
          subject TEXT NOT NULL,
          content TEXT NOT NULL
        );
        CREATE TABLE class_schedule_entries(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          weekday TEXT NOT NULL,
          session_kind TEXT NOT NULL,
          subject TEXT,
          status TEXT NOT NULL
        );
        CREATE TABLE external_source_mappings(
          source_key TEXT PRIMARY KEY,
          spreadsheet_id TEXT,
          sheet_name TEXT,
          payload_json TEXT NOT NULL
        );
        """,
    )
    mapping_payload = {
        "journal_cell_mapping": {
            "spreadsheet_id": "sheet-1",
            "tab_title": "2026년 6월",
            "teacher_block": {"mapped_rows": {"EISS": {"sheet_class": "EISS", "row": 4}}},
            "date_column_map": {"2026-06-24": "Z"},
        },
    }
    conn.execute("INSERT INTO classes VALUES (2, 'EISS', 'EISS')")
    conn.execute(
        """
        INSERT INTO sessions(
          id, class_id, session_kind, session_date, subject, progress, homework, payload_json
        )
        VALUES (596, 2, 'main', '2026-06-24', 'reading', ?, ?, ?)
        """,
        (progress, homework, payload_json),
    )
    conn.executemany(
        "INSERT INTO class_schedule_entries(class_id, weekday, session_kind, subject, status) "
        "VALUES (2, ?, 'main', 'reading', 'active')",
        [("WE",), ("FR",)],
    )
    conn.execute(
        "INSERT INTO external_source_mappings"
        "(source_key, spreadsheet_id, sheet_name, payload_json) "
        "VALUES ('daily_management.2026_06', 'sheet-1', '2026년 6월', ?)",
        (json.dumps(mapping_payload, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()
    return db_path


def test_daily_lesson_homework_items_discover_block_and_same_subject_homework(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "chat_lms.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE classes(
          id INTEGER PRIMARY KEY,
          code TEXT NOT NULL,
          canonical_name TEXT NOT NULL
        );
        CREATE TABLE students(
          id INTEGER PRIMARY KEY,
          canonical_name TEXT NOT NULL,
          attrs_json TEXT NOT NULL DEFAULT '{}',
          active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE sessions(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          session_kind TEXT NOT NULL,
          session_date TEXT NOT NULL,
          subject TEXT,
          progress TEXT,
          homework TEXT,
          payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE student_session_records(
          id INTEGER PRIMARY KEY,
          session_id INTEGER NOT NULL,
          student_id INTEGER NOT NULL,
          attendance TEXT,
          homework_score REAL,
          note TEXT,
          payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE class_schedule_entries(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          weekday TEXT NOT NULL,
          session_kind TEXT NOT NULL,
          subject TEXT,
          status TEXT NOT NULL
        );
        CREATE TABLE external_source_mappings(
          source_key TEXT PRIMARY KEY,
          spreadsheet_id TEXT,
          sheet_name TEXT,
          payload_json TEXT NOT NULL
        );
        """,
    )
    mapping_payload = {
        "spreadsheet_id": "sheet-1",
        "class_alias_map": {"EISS": "EISS"},
        "homework_completion_grade_scale": {
            "allowed_values": ["A+", "A", "B", "C", "D"],
        },
    }
    conn.execute("INSERT INTO classes VALUES (2, 'EISS', 'EISS')")
    conn.executemany(
        "INSERT INTO students(id, canonical_name) VALUES (?, ?)",
        [(5, "Alice"), (6, "Ben")],
    )
    conn.execute(
        """
        INSERT INTO sessions(id, class_id, session_kind, session_date, subject, progress, homework)
        VALUES (579, 2, 'main', '2026-06-15', 'grammar', 'old', 'essay test')
        """,
    )
    conn.execute(
        """
        INSERT INTO sessions(id, class_id, session_kind, session_date, subject, progress, homework)
        VALUES (592, 2, 'main', '2026-06-22', '', '', '')
        """,
    )
    conn.executemany(
        """
        INSERT INTO student_session_records(session_id, student_id, attendance, homework_score)
        VALUES (592, ?, 'present', ?)
        """,
        [(5, 0.0), (6, 100.0)],
    )
    conn.execute(
        """
        INSERT INTO class_schedule_entries(class_id, weekday, session_kind, subject, status)
        VALUES (2, 'MO', 'main', 'grammar', 'active')
        """,
    )
    conn.execute(
        """
        INSERT INTO external_source_mappings(source_key, spreadsheet_id, sheet_name, payload_json)
        VALUES ('daily_lesson_homework.2026_06', 'sheet-1', '1', ?)
        """,
        (json.dumps(mapping_payload, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()
    current_values = {
        "range": "'22'!A1:K80",
        "values": [
            [],
            [],
            ["NO.3", "이름", "반이름", "EISS"],
            [],
            ["", "", "듣기", "", "", "단어", "", "", "숙제", "통계"],
            ["", "", "점수", "총점", "%", "점수", "총점", "%"],
            ["1", "Alice", "", "20", "0%", "", "40", "0%", "", "0%"],
            ["2", "Ben", "", "20", "0%", "", "40", "0%", "", "0%"],
            ["담당 관리자", "", "듣기", "", "", "단어", "", "", "숙제"],
        ],
    }

    items = build_daily_lesson_homework_items(
        db_path,
        source_key="daily_lesson_homework.2026_06",
        lesson_date="2026-06-22",
        current_values_payload=current_values,
        class_codes=("EISS",),
    )

    assert [(item.range_a1, item.target_value) for item in items] == [
        ("'22'!I7", "D"),
        ("'22'!I8", "A+"),
        ("'22'!J9", "essay test"),
    ]
    assert all(item.payload["overwrite_policy"] == "protect_non_empty" for item in items)


def test_daily_lesson_homework_plan_cli_writes_batch_payload(tmp_path: Path) -> None:
    db_path = _create_single_student_daily_homework_db(tmp_path)
    current_values_path = tmp_path / "current.json"
    current_values_path.write_text(
        json.dumps(
            {
                "range": "'22'!A1:K80",
                "values": [
                    ["NO.3", "이름", "반이름", "EISS"],
                    [],
                    [],
                    [],
                    ["1", "Ben", "", "20", "0%", "", "40", "0%", "", "0%"],
                    ["담당 관리자", "", "듣기", "", "", "단어", "", "", "숙제"],
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    result = main(
        [
            "outbound",
            "daily-lesson-homework",
            "plan",
            "--database",
            str(db_path),
            "--date",
            "2026-06-22",
            "--classes",
            "EISS",
            "--current-values-json",
            str(current_values_path),
            "--out-dir",
            str(out_dir),
            "--json",
        ],
    )

    assert result == 0
    payload = json.loads((out_dir / "batch_update_payload.json").read_text(encoding="utf-8"))
    assert payload["data"] == [
        {"range": "'22'!I5", "values": [["A+"]]},
        {"range": "'22'!J6", "values": [["essay test"]]},
    ]


def test_daily_lesson_homework_sync_dry_run_reads_live_values_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = _create_single_student_daily_homework_db(tmp_path)
    current_values = {
        "range": "'22'!A1:K80",
        "values": [
            ["NO.3", "이름", "반이름", "EISS"],
            [],
            [],
            [],
            ["1", "Ben", "", "20", "0%", "", "40", "0%", "", "0%"],
            ["담당 관리자", "", "듣기", "", "", "단어", "", "", "숙제"],
        ],
    }

    read_ranges: list[str] = []

    def fake_access_token(_path: Path) -> str:
        return "token"

    def fake_values_get(_access: str, _sheet_id: str, range_name: str) -> dict[str, object]:
        read_ranges.append(range_name)
        return current_values

    def fail_batch_update(_access: str, _sheet_id: str, _data: object) -> object:
        message = "dry-run wrote to sheet"
        raise AssertionError(message)

    monkeypatch.setattr(
        daily_lesson_homework_handlers,
        "load_valid_access_token",
        fake_access_token,
    )
    monkeypatch.setattr(
        daily_lesson_homework_handlers,
        "sheets_values_get",
        fake_values_get,
    )
    monkeypatch.setattr(
        daily_lesson_homework_handlers,
        "sheets_batch_update",
        fail_batch_update,
    )
    out_dir = tmp_path / "sync"

    result = main(
        [
            "outbound",
            "daily-lesson-homework",
            "sync",
            "--database",
            str(db_path),
            "--date",
            "2026-06-22",
            "--classes",
            "EISS",
            "--out-dir",
            str(out_dir),
            "--json",
        ],
    )

    assert result == 0
    stdout_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(stdout_lines) == 1
    payload = json.loads(stdout_lines[0])
    assert payload["execute_required"] is True
    assert payload["summary"] == {"total": 2, "write_changed": 2}
    assert read_ranges == ["'22'!A1:K1000"]


def test_daily_lesson_homework_sync_blocks_writes_conflict_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = _create_single_student_daily_homework_db(tmp_path)
    # Ben's homework grade cell (I5) already holds a different non-empty grade -> conflict.
    current_values = {
        "range": "'22'!A1:K80",
        "values": [
            ["NO.3", "이름", "반이름", "EISS"],
            [],
            [],
            [],
            ["1", "Ben", "", "20", "0%", "", "40", "0%", "C", "0%"],
            ["담당 관리자", "", "듣기", "", "", "단어", "", "", "숙제"],
        ],
    }

    def fake_access_token(_path: Path) -> str:
        return "token"

    def fake_values_get(_access: str, _sheet_id: str, _range_name: str) -> dict[str, object]:
        return current_values

    def fail_batch_update(_access: str, _sheet_id: str, _updates: object) -> object:
        message = "must not write while conflicted"
        raise AssertionError(message)

    monkeypatch.setattr(
        daily_lesson_homework_handlers,
        "load_valid_access_token",
        fake_access_token,
    )
    monkeypatch.setattr(daily_lesson_homework_handlers, "sheets_values_get", fake_values_get)
    monkeypatch.setattr(daily_lesson_homework_handlers, "sheets_batch_update", fail_batch_update)
    out_dir = tmp_path / "sync"

    result = main(
        [
            "outbound",
            "daily-lesson-homework",
            "sync",
            "--database",
            str(db_path),
            "--date",
            "2026-06-22",
            "--classes",
            "EISS",
            "--out-dir",
            str(out_dir),
            "--execute",
            "--json",
        ],
    )

    assert result == 5
    stdout_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    payload = json.loads(stdout_lines[-1])
    assert payload["status"] == "BLOCKED"
    assert "conflict_report" in payload
    report = json.loads((out_dir / "conflict_report.json").read_text(encoding="utf-8"))
    assert report["count"] >= 1
    assert any(conflict["current"] == "C" for conflict in report["conflicts"])


def _create_daily_management_sync_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "chat_lms.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE classes(
          id INTEGER PRIMARY KEY,
          code TEXT NOT NULL,
          canonical_name TEXT NOT NULL
        );
        CREATE TABLE sessions(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          session_kind TEXT NOT NULL,
          session_date TEXT NOT NULL,
          subject TEXT,
          progress TEXT,
          homework TEXT,
          payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE curriculum_entries(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          planned_on TEXT NOT NULL,
          subject TEXT NOT NULL,
          content TEXT NOT NULL
        );
        CREATE TABLE class_schedule_entries(
          id INTEGER PRIMARY KEY,
          class_id INTEGER NOT NULL,
          weekday TEXT NOT NULL,
          session_kind TEXT NOT NULL,
          subject TEXT,
          status TEXT NOT NULL
        );
        CREATE TABLE external_source_mappings(
          source_key TEXT PRIMARY KEY,
          spreadsheet_id TEXT,
          sheet_name TEXT,
          payload_json TEXT NOT NULL
        );
        """,
    )
    mapping_payload = {
        "journal_cell_mapping": {
            "spreadsheet_id": "sheet-1",
            "tab_title": "2026년 6월",
            "teacher_block": {"mapped_rows": {"EBSS": {"sheet_class": "EBSS", "row": 2}}},
            "date_column_map": {"2026-06-01": "C"},
        },
    }
    conn.execute("INSERT INTO classes VALUES (45, 'EBSS', 'EBSS')")
    conn.execute(
        """
        INSERT INTO sessions(id, class_id, session_kind, session_date, subject, progress, homework)
        VALUES (559, 45, 'main', '2026-06-01', 'reading', 'Unit 1', 'Student Book p.9')
        """,
    )
    conn.execute(
        """
        INSERT INTO curriculum_entries(class_id, planned_on, subject, content)
        VALUES (45, '2026-06-01', 'vocabulary', 'LV.1 Unit 1')
        """,
    )
    conn.execute(
        """
        INSERT INTO class_schedule_entries(class_id, weekday, session_kind, subject, status)
        VALUES (45, 'MO', 'main', 'reading', 'active')
        """,
    )
    conn.execute(
        """
        INSERT INTO external_source_mappings(source_key, spreadsheet_id, sheet_name, payload_json)
        VALUES ('daily_management.2026_06', 'sheet-1', '2026년 6월', ?)
        """,
        (json.dumps(mapping_payload, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()
    return db_path


def _grid_from_updates(read_range: str, updates: list[dict[str, object]]) -> dict[str, object]:
    cells: dict[tuple[int, int], str] = {}
    for update in updates:
        ref = str(update["range"]).split("!", 1)[-1]
        letters = "".join(char for char in ref if char.isalpha()).upper()
        row = int("".join(char for char in ref if char.isdigit()))
        col = 0
        for char in letters:
            col = (col * 26) + ord(char) - 64
        values = update["values"]
        cells[(row, col)] = str(values[0][0])  # type: ignore[index]
    max_row = max(row for row, _ in cells)
    max_col = max(col for _, col in cells)
    grid: list[list[str]] = [["" for _ in range(max_col)] for _ in range(max_row)]
    for (row, col), value in cells.items():
        grid[row - 1][col - 1] = value
    return {"range": read_range, "values": grid}


def test_daily_management_sync_dry_run_reads_live_values_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = _create_daily_management_sync_db(tmp_path)
    current_values = {"range": "'2026년 6월'!A1:C2", "values": [[], []]}
    read_ranges: list[str] = []

    def fake_access_token(_path: Path) -> str:
        return "token"

    def fake_values_get(_access: str, _sheet_id: str, range_name: str) -> dict[str, object]:
        read_ranges.append(range_name)
        return current_values

    def fail_batch_update(_access: str, _sheet_id: str, _updates: object) -> object:
        message = "dry-run wrote to sheet"
        raise AssertionError(message)

    monkeypatch.setattr(outbound_handlers, "load_valid_access_token", fake_access_token)
    monkeypatch.setattr(outbound_handlers, "sheets_values_get", fake_values_get)
    monkeypatch.setattr(outbound_handlers, "sheets_batch_update", fail_batch_update)
    out_dir = tmp_path / "sync"

    result = main(
        [
            "outbound",
            "daily-management",
            "sync",
            "--database",
            str(db_path),
            "--date",
            "2026-06-01",
            "--out-dir",
            str(out_dir),
            "--json",
        ],
    )

    assert result == 0
    stdout_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(stdout_lines) == 1
    payload = json.loads(stdout_lines[0])
    assert payload["execute_required"] is True
    assert payload["summary"] == {"total": 2, "write_changed": 2}
    assert read_ranges == ["'2026년 6월'!A1:C2"]
    data = json.loads((out_dir / "batch_update_payload.json").read_text(encoding="utf-8"))
    assert [entry["range"] for entry in data["data"]] == ["'2026년 6월'!B2", "'2026년 6월'!C2"]


def test_daily_management_sync_execute_writes_verifies_and_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = _create_daily_management_sync_db(tmp_path)
    pre = {"range": "'2026년 6월'!A1:C2", "values": [[], []]}
    captured: dict[str, object] = {"updates": None}
    read_ranges: list[str] = []

    def fake_access_token(_path: Path) -> str:
        return "token"

    def fake_batch_update(
        _access: str,
        sheet_id: str,
        updates: list[dict[str, object]],
    ) -> dict[str, object]:
        captured["updates"] = updates
        return {"spreadsheetId": sheet_id, "totalUpdatedCells": len(updates)}

    def fake_values_get(_access: str, _sheet_id: str, range_name: str) -> dict[str, object]:
        read_ranges.append(range_name)
        if captured["updates"] is None:
            return pre
        return _grid_from_updates(range_name, cast("list[dict[str, object]]", captured["updates"]))

    monkeypatch.setattr(outbound_handlers, "load_valid_access_token", fake_access_token)
    monkeypatch.setattr(outbound_handlers, "sheets_values_get", fake_values_get)
    monkeypatch.setattr(outbound_handlers, "sheets_batch_update", fake_batch_update)
    out_dir = tmp_path / "sync"

    result = main(
        [
            "outbound",
            "daily-management",
            "sync",
            "--database",
            str(db_path),
            "--date",
            "2026-06-01",
            "--out-dir",
            str(out_dir),
            "--execute",
            "--json",
        ],
    )

    assert result == 0
    stdout_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    payload = json.loads(stdout_lines[-1])
    assert payload["status"] == "PASS"
    assert payload["verified"] == 2
    assert payload["recorded"] == 2
    updates = cast("list[dict[str, object]]", captured["updates"])
    assert [str(update["range"]) for update in updates] == ["'2026년 6월'!B2", "'2026년 6월'!C2"]
    assert read_ranges == ["'2026년 6월'!A1:C2", "'2026년 6월'!A1:C2"]
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT count(*) FROM external_outbound_ledger").fetchone()[0]
    conn.close()
    assert count == 2


def test_daily_management_sync_blocks_on_review_conflict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = _create_daily_management_sync_db(tmp_path)
    pre = {"range": "'2026년 6월'!A1:C2", "values": [[], ["", "", "manual teacher edit"]]}

    def fake_access_token(_path: Path) -> str:
        return "token"

    def fake_values_get(_access: str, _sheet_id: str, _range_name: str) -> dict[str, object]:
        return pre

    def fail_batch_update(_access: str, _sheet_id: str, _updates: object) -> object:
        message = "must not write while conflicted"
        raise AssertionError(message)

    monkeypatch.setattr(outbound_handlers, "load_valid_access_token", fake_access_token)
    monkeypatch.setattr(outbound_handlers, "sheets_values_get", fake_values_get)
    monkeypatch.setattr(outbound_handlers, "sheets_batch_update", fail_batch_update)
    out_dir = tmp_path / "sync"

    result = main(
        [
            "outbound",
            "daily-management",
            "sync",
            "--database",
            str(db_path),
            "--date",
            "2026-06-01",
            "--out-dir",
            str(out_dir),
            "--execute",
            "--json",
        ],
    )

    assert result == 5
    stdout_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    payload = json.loads(stdout_lines[-1])
    assert payload["status"] == "BLOCKED"
    assert payload["error_code"] == "OUTBOUND_REVIEW_CONFLICT"
    assert payload["summary"]["review_conflict"] == 1
    assert "conflict_report" in payload
    report = json.loads((out_dir / "conflict_report.json").read_text(encoding="utf-8"))
    assert report["count"] == 1
    assert report["conflicts"][0]["range"] == "'2026년 6월'!C2"
    assert report["conflicts"][0]["current"] == "manual teacher edit"


def test_daily_management_sync_execute_fails_when_write_does_not_land(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = _create_daily_management_sync_db(tmp_path)
    pre = {"range": "'2026년 6월'!A1:C2", "values": [[], []]}
    captured: dict[str, object] = {"updates": None}

    def fake_access_token(_path: Path) -> str:
        return "token"

    def fake_batch_update(
        _access: str,
        sheet_id: str,
        updates: list[dict[str, object]],
    ) -> dict[str, object]:
        captured["updates"] = updates
        return {"spreadsheetId": sheet_id}

    def fake_values_get(_access: str, _sheet_id: str, range_name: str) -> dict[str, object]:
        if captured["updates"] is None:
            return pre
        # Post-read shows empty cells: the write did not land, so verification must fail.
        return {"range": range_name, "values": [[], []]}

    monkeypatch.setattr(outbound_handlers, "load_valid_access_token", fake_access_token)
    monkeypatch.setattr(outbound_handlers, "sheets_values_get", fake_values_get)
    monkeypatch.setattr(outbound_handlers, "sheets_batch_update", fake_batch_update)
    out_dir = tmp_path / "sync"

    result = main(
        [
            "outbound",
            "daily-management",
            "sync",
            "--database",
            str(db_path),
            "--date",
            "2026-06-01",
            "--out-dir",
            str(out_dir),
            "--execute",
            "--json",
        ],
    )

    assert result == 6
    stdout_lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    payload = json.loads(stdout_lines[-1])
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "OUTBOUND_VERIFY_FAILED"
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT count(*) FROM external_outbound_ledger").fetchone()[0]
    conn.close()
    assert count == 0


def test_current_values_from_json_unwraps_cli_envelope() -> None:
    raw = {"range": "'6월'!A1:B2", "values": [["x", "y"]]}
    envelope = {"status": "PASS", "result": raw, "out": "out.json"}

    assert current_values_from_json(envelope) == current_values_from_json(raw)
    assert current_values_from_json(envelope) == {"A1": "x", "B1": "y"}


def test_daily_management_journal_renders_gold_three_block_format(tmp_path: Path) -> None:
    """Golden test for the parent-facing journal gold format.

    Three blocks (과제 및 테스트 / 수업 / 과제 및 테스트) with the textbook header, the
    listening line, and BOTH homework cross-references with date ranges: block-1 H) =
    previous SAME-SUBJECT session's homework (skipping the more-recent reading
    sessions); block-3 H) = today's homework due at the next SAME-SUBJECT meeting
    (6/29, not the next class day 6/24). The planned chapter (Ch06) is never shown.
    """
    db_path = tmp_path / "chat_lms.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE classes(
          id INTEGER PRIMARY KEY, code TEXT NOT NULL, canonical_name TEXT NOT NULL
        );
        CREATE TABLE sessions(
          id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, session_kind TEXT NOT NULL,
          session_date TEXT NOT NULL, subject TEXT, progress TEXT, homework TEXT,
          payload_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE curriculum_entries(
          id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, planned_on TEXT NOT NULL,
          subject TEXT NOT NULL, content TEXT NOT NULL
        );
        CREATE TABLE class_schedule_entries(
          id INTEGER PRIMARY KEY, class_id INTEGER NOT NULL, weekday TEXT NOT NULL,
          session_kind TEXT NOT NULL, subject TEXT, status TEXT NOT NULL
        );
        CREATE TABLE external_source_mappings(
          source_key TEXT PRIMARY KEY, spreadsheet_id TEXT,
          sheet_name TEXT, payload_json TEXT NOT NULL
        );
        """,
    )
    mapping_payload = {
        "journal_cell_mapping": {
            "spreadsheet_id": "sheet-1",
            "tab_title": "2026년 6월",
            "teacher_block": {"mapped_rows": {"EISS": {"sheet_class": "EISS", "row": 4}}},
            "date_column_map": {"2026-06-22": "X"},
        },
    }
    today_hw = "Ch 05 조동사 5-4까지(~ p.107) 풀기"
    conn.execute("INSERT INTO classes VALUES (2, 'EISS', 'EISS')")
    conn.executemany(
        "INSERT INTO sessions"
        "(id, class_id, session_kind, session_date, subject, progress, homework) "
        "VALUES (?, 2, 'main', ?, ?, ?, ?)",
        [
            (615, "2026-06-15", "grammar", "ch04", "서술형 평가"),
            (617, "2026-06-17", "reading", "u10", "unit 10 workbook"),
            (619, "2026-06-19", "reading", "", ""),
            (700, "2026-06-22", "grammar", "Ch 05 조동사 5-4", today_hw),
        ],
    )
    conn.executemany(
        "INSERT INTO curriculum_entries(class_id, planned_on, subject, content) "
        "VALUES (2, ?, ?, ?)",
        [
            ("2026-06-22", "vocabulary", "LV.1 6B 1~2 (뜻)\nLV.2 7A ALL(R:100)"),
            ("2026-06-22", "listening", "개인별 맞춤 듣기"),
            ("2026-06-22", "문법", "Bricks 중등문법 1\nCh06 형용사"),
            ("2026-06-24", "vocabulary", "LV.1 6B 1~2 (뜻,스펠 반반)\nLV.2 7A ALL(R:100)"),
            ("2026-06-24", "listening", "개인별 맞춤 듣기"),
        ],
    )
    conn.executemany(
        "INSERT INTO class_schedule_entries(class_id, weekday, session_kind, subject, status) "
        "VALUES (2, ?, 'main', ?, 'active')",
        [("MO", "grammar"), ("WE", "reading"), ("FR", "reading")],
    )
    conn.execute(
        "INSERT INTO external_source_mappings"
        "(source_key, spreadsheet_id, sheet_name, payload_json) "
        "VALUES ('daily_management.2026_06', 'sheet-1', '2026년 6월', ?)",
        (json.dumps(mapping_payload, ensure_ascii=False),),
    )
    conn.commit()
    conn.close()

    items = build_daily_management_journal_items(
        db_path,
        source_key="daily_management.2026_06",
        start_date="2026-06-22",
        end_date="2026-06-22",
        current_values={},
        include_label_items=False,
    )

    assert len(items) == 1
    expected = (
        "6/22 과제 및 테스트\n"
        "1. LV.1 6B 1~2 (뜻)\n"
        "LV.2 7A ALL(R:100)\n"
        "2. 개인별 맞춤 듣기\n"
        "H) 서술형 평가 (6/15~6/22)\n"
        "-------------------\n"
        "6/22 수업\n"
        "(문법) Bricks 중등문법 1\n"
        "1. Ch 05 조동사 5-4\n"
        "-------------------\n"
        "6/24 과제 및 테스트\n"
        "1. LV.1 6B 1~2 (뜻,스펠 반반)\n"
        "LV.2 7A ALL(R:100)\n"
        "2. 개인별 맞춤 듣기\n"
        f"H) {today_hw} (6/22~6/29)"
    )
    assert str(items[0].target_value) == expected
