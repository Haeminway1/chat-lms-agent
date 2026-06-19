from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING

from chat_lms_agent.commands import main
from chat_lms_agent.outbound_sync import (
    OutboundItem,
    build_plan,
    content_hash,
    ensure_outbound_ledger,
    idempotency_key,
    normalize_for_hash,
    record_outbound_result,
)
from chat_lms_agent.daily_management_outbound import (
    build_daily_management_journal_items,
)

if TYPE_CHECKING:
    from pathlib import Path

EXPECTED_JOURNAL_KEY = (
    "daily_management.2026_06|session_journal|class:EBSS,session:42|"
    "2026-06|append_row|v1"
)


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
        """
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
        """
    )
    conn.execute(
        """
        INSERT INTO curriculum_entries(class_id, planned_on, subject, content)
        VALUES (45, '2026-06-01', 'vocabulary', 'LV.1 Synthetic Unit 1')
        """
    )
    conn.execute(
        """
        INSERT INTO class_schedule_entries(class_id, weekday, session_kind, subject, status)
        VALUES (45, 'FR', 'main', 'reading', 'active')
        """
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
    assert item.target_value.startswith("EBSS\n\n6/1 TEST\nLV.1 Synthetic Unit 1")

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
