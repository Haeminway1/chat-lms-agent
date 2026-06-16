from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from chat_lms_agent.state import ProfileState
from chat_lms_agent.write_actions import WriteActionTemplate, WriteStep
from chat_lms_agent.write_engine import run_write_action

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

TABLES = (
    "classes",
    "students",
    "enrollments",
    "sessions",
    "student_session_records",
    "tests",
    "test_results",
    "curriculum_entries",
)


@dataclass(frozen=True, slots=True)
class DbFixture:
    profile: ProfileState
    db_path: Path
    student_ids: dict[str, int]


class _ConnectRecorder:
    def __init__(self) -> None:
        self.calls: list[Path] = []
        self.isolation_levels: list[str | None] = []

    def __call__(self, db_path: str | Path) -> sqlite3.Connection:
        path = Path(db_path)
        self.calls.append(path)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        self.isolation_levels.append(conn.isolation_level)
        return conn


def test_run_write_action_updates_trigger_stubs_without_duplicates(tmp_path: Path) -> None:
    # Given: active enrollments that cause the sessions trigger to create stub records.
    fixture = _fixture(tmp_path)
    recorder = _ConnectRecorder()
    params = _params(fixture, students=("Fictional Ada", "Fictional Ben"))

    # When: the generic write action runs.
    code, payload = run_write_action(
        fixture.profile,
        _record_class_template(),
        params,
        db_path=fixture.db_path,
        connect=recorder,
        now=lambda: "20260616T010203Z",
    )

    # Then: trigger-created rows are updated in place, not duplicated.
    assert code == 0
    assert payload["status"] == "PASS"
    with sqlite3.connect(fixture.db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = cast(
            "list[sqlite3.Row]",
            conn.execute(
                """
                SELECT r.student_id, r.attendance, r.homework_score, r.note, r.payload_json
                FROM student_session_records r
                ORDER BY r.student_id
                """,
            ).fetchall(),
        )
    assert len(rows) == 2
    assert [row["attendance"] for row in rows] == ["present", "late"]
    assert [_json_source(_row_str(row, "payload_json")) for row in rows] == [
        "teacher_prompt",
        "teacher_prompt",
    ]
    assert rows[0]["note"] == "@session_id"
    captured_ids = payload["captured_ids"]
    assert isinstance(captured_ids, dict)
    assert captured_ids["session_id"] == 1
    assert recorder.calls == [fixture.db_path.resolve()]


def test_run_write_action_repairs_null_attendance_stub(tmp_path: Path) -> None:
    # Given: the trigger creates a student-session stub with attendance NULL.
    fixture = _fixture(tmp_path)

    # When: update_stub runs for the enrolled student.
    code, _payload = run_write_action(
        fixture.profile,
        _record_class_template(),
        _params(fixture, students=("Fictional Ada",)),
        db_path=fixture.db_path,
        connect=_ConnectRecorder(),
        now=lambda: "20260616T010204Z",
    )

    # Then: the NULL attendance is repaired by UPDATE.
    assert code == 0
    with sqlite3.connect(fixture.db_path) as conn:
        attendance = _select_scalar_str(
            conn,
            "SELECT attendance FROM student_session_records WHERE student_id = ?",
            (fixture.student_ids["Fictional Ada"],),
        )
    assert attendance == "present"


def test_run_write_action_allows_explicit_makeup_insert_without_stub(tmp_path: Path) -> None:
    # Given: a make-up student exists but is not actively enrolled, so no trigger stub exists.
    fixture = _fixture(tmp_path, include_makeup=True)
    params = _params(
        fixture,
        students=("Fictional Ada",),
        makeups=("Fictional Cora",),
    )

    # When: the template uses its documented explicit insert path for make-ups.
    code, payload = run_write_action(
        fixture.profile,
        _record_class_template(),
        params,
        db_path=fixture.db_path,
        connect=_ConnectRecorder(),
        now=lambda: "20260616T010205Z",
    )

    # Then: the non-enrolled student receives exactly one explicit record.
    assert code == 0
    assert isinstance(payload["rows_affected"], int)
    assert payload["rows_affected"] >= 1
    with sqlite3.connect(fixture.db_path) as conn:
        rows = conn.execute(
            """
            SELECT student_id, attendance
            FROM student_session_records
            WHERE student_id = ?
            """,
            (fixture.student_ids["Fictional Cora"],),
        ).fetchall()
    assert rows == [(fixture.student_ids["Fictional Cora"], "present")]


def test_run_write_action_rolls_back_mid_transaction_failure_and_keeps_backup(
    tmp_path: Path,
) -> None:
    # Given: a template that fails after inserting the session.
    fixture = _fixture(tmp_path)
    before = _table_counts(fixture.db_path)
    before_dump = _db_dump(fixture.db_path)
    params = _params(fixture, students=("Fictional Ada",))

    # When: a later SQL step violates a foreign key.
    code, payload = run_write_action(
        fixture.profile,
        _failing_template(),
        params,
        db_path=fixture.db_path,
        connect=_ConnectRecorder(),
        now=lambda: "20260616T010206Z",
    )

    # Then: every table count is restored and the pre-write backup remains.
    assert code == 2
    assert payload == {
        "status": "ERROR",
        "error_code": "WRITE_FAILED",
        "step_id": "insert_bad_result",
    }
    assert _table_counts(fixture.db_path) == before
    assert _db_dump(fixture.db_path) == before_dump
    backup = fixture.profile.root / ".chat-lms-state/write-actions/backups/20260616T010206Z.sqlite3"
    assert backup.exists()


def test_run_write_action_creates_binary_safe_backup_of_pinned_db(tmp_path: Path) -> None:
    # Given: a real SQLite file under the profile root.
    fixture = _fixture(tmp_path)

    # When: the write engine backs it up before writing.
    code, payload = run_write_action(
        fixture.profile,
        _record_class_template(),
        _params(fixture, students=("Fictional Ada",)),
        db_path=fixture.db_path,
        connect=_ConnectRecorder(),
        now=lambda: "20260616T010207Z",
    )

    # Then: the backup is a valid SQLite copy of the original pinned database.
    assert code == 0
    backup = Path(str(payload["backup"]))
    assert backup == (
        fixture.profile.root / ".chat-lms-state/write-actions/backups/20260616T010207Z.sqlite3"
    )
    with sqlite3.connect(backup) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT count(*) FROM classes").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 0


def test_run_write_action_pins_db_path_before_connect_or_backup(tmp_path: Path) -> None:
    # Given: profile, repo, and out-of-profile paths.
    fixture = _fixture(tmp_path)
    outside_db = tmp_path / "outside.sqlite3"
    repo_db = fixture.profile.repo_root / "repo.sqlite3"
    profile_non_data_db = fixture.profile.root / "chat_lms.db"

    # When: unsafe paths are passed.
    outside_recorder = _ConnectRecorder()
    outside_code, outside_payload = run_write_action(
        fixture.profile,
        _record_class_template(),
        _params(fixture, students=("Fictional Ada",)),
        db_path=outside_db,
        connect=outside_recorder,
        now=lambda: "20260616T010208Z",
    )
    repo_recorder = _ConnectRecorder()
    repo_code, repo_payload = run_write_action(
        fixture.profile,
        _record_class_template(),
        _params(fixture, students=("Fictional Ada",)),
        db_path=repo_db,
        connect=repo_recorder,
        now=lambda: "20260616T010209Z",
    )
    non_data_recorder = _ConnectRecorder()
    non_data_code, non_data_payload = run_write_action(
        fixture.profile,
        _record_class_template(),
        _params(fixture, students=("Fictional Ada",)),
        db_path=profile_non_data_db,
        connect=non_data_recorder,
        now=lambda: "20260616T010215Z",
    )

    # Then: unsafe paths are rejected without opening a connection.
    assert (outside_code, outside_payload) == (
        4,
        {"status": "UNSAFE", "error_code": "DB_PATH_OUT_OF_PROFILE"},
    )
    assert (repo_code, repo_payload) == (
        4,
        {"status": "UNSAFE", "error_code": "DB_PATH_OUT_OF_PROFILE"},
    )
    assert (non_data_code, non_data_payload) == (
        4,
        {"status": "UNSAFE", "error_code": "DB_PATH_OUT_OF_PROFILE"},
    )
    assert outside_recorder.calls == []
    assert repo_recorder.calls == []
    assert non_data_recorder.calls == []


def test_run_write_action_returns_plan_error_without_connecting(tmp_path: Path) -> None:
    # Given: params fail template compilation before any DB side effect is allowed.
    fixture = _fixture(tmp_path)
    recorder = _ConnectRecorder()

    # When: required params are missing.
    code, payload = run_write_action(
        fixture.profile,
        _record_class_template(),
        {},
        db_path=fixture.db_path,
        connect=recorder,
        now=lambda: "20260616T010216Z",
    )

    # Then: the error is returned without opening or backing up the database.
    assert code == 2
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "INVALID_PARAMS"
    errors = payload["errors"]
    assert isinstance(errors, list)
    assert "MISSING_PARAM: class_code" in errors
    assert recorder.calls == []
    assert not (fixture.profile.root / ".chat-lms-state/write-actions/backups").exists()


def test_run_write_action_accepts_db_path_under_profile_data(tmp_path: Path) -> None:
    # Given: the synthetic database lives under profile.root/data.
    fixture = _fixture(tmp_path)
    recorder = _ConnectRecorder()

    # When: the write engine runs.
    code, payload = run_write_action(
        fixture.profile,
        _record_class_template(),
        _params(fixture, students=("Fictional Ada",)),
        db_path=fixture.db_path,
        connect=recorder,
        now=lambda: "20260616T010210Z",
    )

    # Then: the pinned path is accepted and opened exactly once.
    assert code == 0
    assert payload["status"] == "PASS"
    assert recorder.calls == [fixture.db_path.resolve()]


def test_run_write_action_lookup_miss_rolls_back_for_unknown_class(tmp_path: Path) -> None:
    # Given: no class exists for the requested code.
    fixture = _fixture(tmp_path)
    before = _table_counts(fixture.db_path)
    params = {**_params(fixture, students=("Fictional Ada",)), "class_code": "missing"}

    # When: the first resolve step misses.
    code, payload = run_write_action(
        fixture.profile,
        _record_class_template(),
        params,
        db_path=fixture.db_path,
        connect=_ConnectRecorder(),
        now=lambda: "20260616T010211Z",
    )

    # Then: no partial write remains.
    assert code == 2
    assert payload == {
        "status": "ERROR",
        "error_code": "LOOKUP_MISS",
        "step_id": "resolve_class",
    }
    assert _table_counts(fixture.db_path) == before


def test_run_write_action_lookup_miss_rolls_back_for_unknown_student(tmp_path: Path) -> None:
    # Given: a template resolves a student by name before writing.
    fixture = _fixture(tmp_path)
    before = _table_counts(fixture.db_path)

    # When: the requested synthetic student is absent.
    code, payload = run_write_action(
        fixture.profile,
        _student_lookup_template(),
        {"student_name": "Fictional Missing"},
        db_path=fixture.db_path,
        connect=_ConnectRecorder(),
        now=lambda: "20260616T010212Z",
    )

    # Then: the lookup miss is explicit and no write leaks through.
    assert code == 2
    assert payload == {
        "status": "ERROR",
        "error_code": "LOOKUP_MISS",
        "step_id": "resolve_student",
    }
    assert _table_counts(fixture.db_path) == before


def test_run_write_action_keeps_transaction_isolation_level_for_rollback(tmp_path: Path) -> None:
    # Given: a failing plan and a recorder for connection isolation state.
    fixture = _fixture(tmp_path)
    recorder = _ConnectRecorder()

    # When: execution fails inside the transaction.
    code, _payload = run_write_action(
        fixture.profile,
        _failing_template(),
        _params(fixture, students=("Fictional Ada",)),
        db_path=fixture.db_path,
        connect=recorder,
        now=lambda: "20260616T010213Z",
    )

    # Then: the connection was not in autocommit mode.
    assert code == 2
    assert recorder.isolation_levels == [""]


def test_run_write_action_fans_out_and_journals_only_ids_and_counts(tmp_path: Path) -> None:
    # Given: two students and one test result fan out through array bindings.
    fixture = _fixture(tmp_path)
    params = _params(fixture, students=("Fictional Ada", "Fictional Ben"))

    # When: the action succeeds.
    code, payload = run_write_action(
        fixture.profile,
        _record_class_template(),
        params,
        db_path=fixture.db_path,
        connect=_ConnectRecorder(),
        now=lambda: "20260616T010214Z",
    )

    # Then: fan-out inserted two test results and journals reveal no learner names or scores.
    assert code == 0
    assert isinstance(payload["rows_affected"], int)
    assert payload["rows_affected"] >= 2
    with sqlite3.connect(fixture.db_path) as conn:
        assert conn.execute("SELECT count(*) FROM test_results").fetchone()[0] == 2
    audit_records = _json_records(fixture.profile.root / ".chat-lms-state" / "audit")
    trace_records = _json_records(fixture.profile.root / ".chat-lms-state" / "trace")
    assert len(audit_records) == 1
    assert len(trace_records) == 1
    assert audit_records[0]["audit_id"]
    assert trace_records[0]["trace_id"]
    assert audit_records[0]["operation"] == "write_action"
    assert trace_records[0]["event_type"] == "write_action"
    assert audit_records[0]["details"] == trace_records[0]["details"]
    details = audit_records[0]["details"]
    assert isinstance(details, dict)
    assert details["action_id"] == "record-class"
    assert isinstance(details["rows_affected_per_step"], list)
    assert all(isinstance(item, int) for item in details["rows_affected_per_step"])
    assert details["captured_ids"] == payload["captured_ids"]
    details_text = json.dumps(details, sort_keys=True)
    assert "Fictional Ada" not in details_text
    assert "Fictional Ben" not in details_text
    assert "88" not in details_text
    assert "72" not in details_text
    assert "rows_affected_per_step" in details_text
    assert "captured_ids" in details_text


def _fixture(
    tmp_path: Path,
    *,
    include_makeup: bool = False,
) -> DbFixture:
    repo_root = (tmp_path / "repo").resolve()
    profile_root = (tmp_path / "profile").resolve()
    db_path = profile_root / "data" / "chat_lms.db"
    repo_root.mkdir()
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        _ = conn.executescript(_ddl())
        _ = conn.execute(
            "INSERT INTO classes(code, canonical_name) VALUES (?, ?)",
            ("alpha", "Fictional Alpha Class"),
        )
        student_ids: dict[str, int] = {}
        for name in ("Fictional Ada", "Fictional Ben", "Fictional Cora"):
            if name == "Fictional Cora" and not include_makeup:
                continue
            cursor = conn.execute("INSERT INTO students(canonical_name) VALUES (?)", (name,))
            assert cursor.lastrowid is not None
            student_ids[name] = cursor.lastrowid
        class_id = _select_scalar_int(conn, "SELECT id FROM classes WHERE code = 'alpha'", ())
        for name in ("Fictional Ada", "Fictional Ben"):
            if name in student_ids:
                _ = conn.execute(
                    "INSERT INTO enrollments(student_id, class_id, status) VALUES (?, ?, ?)",
                    (student_ids[name], class_id, "active"),
                )
        conn.commit()
    return DbFixture(
        profile=ProfileState(root=profile_root, repo_root=repo_root),
        db_path=db_path,
        student_ids=student_ids,
    )


def _ddl() -> str:
    return """
    PRAGMA foreign_keys = ON;
    CREATE TABLE classes(id INTEGER PRIMARY KEY, code TEXT UNIQUE, canonical_name TEXT);
    CREATE TABLE students(id INTEGER PRIMARY KEY, canonical_name TEXT UNIQUE);
    CREATE TABLE enrollments(
      id INTEGER PRIMARY KEY,
      student_id INTEGER,
      class_id INTEGER,
      status TEXT
    );
    CREATE TABLE sessions(
      id INTEGER PRIMARY KEY,
      class_id INTEGER,
      session_kind TEXT DEFAULT 'main',
      session_date TEXT,
      subject TEXT,
      progress TEXT,
      homework TEXT,
      payload_json TEXT
    );
    CREATE TABLE student_session_records(
      id INTEGER PRIMARY KEY,
      session_id INTEGER,
      student_id INTEGER,
      attendance TEXT,
      homework_score REAL,
      note TEXT,
      payload_json TEXT,
      UNIQUE(session_id, student_id)
    );
    CREATE TABLE tests(id INTEGER PRIMARY KEY, name TEXT UNIQUE, kind TEXT);
    CREATE TABLE test_results(
      id INTEGER PRIMARY KEY,
      student_id INTEGER,
      session_id INTEGER,
      test_id INTEGER,
      correct INTEGER,
      total INTEGER,
      pct REAL,
      FOREIGN KEY(test_id) REFERENCES tests(id)
    );
    CREATE TABLE curriculum_entries(
      id INTEGER PRIMARY KEY,
      class_id INTEGER,
      planned_on TEXT,
      subject TEXT,
      content TEXT
    );
    CREATE TRIGGER trg_sessions_auto_student_session_records
    AFTER INSERT ON sessions
    BEGIN
      INSERT INTO student_session_records(session_id, student_id, payload_json)
      SELECT NEW.id, e.student_id, '{"source":"auto_enrollment_trigger"}'
      FROM enrollments e WHERE e.class_id = NEW.class_id AND e.status='active';
    END;
    """


def _params(
    fixture: DbFixture,
    *,
    students: tuple[str, ...],
    makeups: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    student_rows: list[JsonValue] = []
    for index, name in enumerate(students):
        student_rows.append(
            {
                "student_id": fixture.student_ids[name],
                "attendance": "present" if index == 0 else "late",
                "homework_score": 88 if index == 0 else 72,
                "note": "@session_id" if index == 0 else "fictional note",
                "payload_json": '{"source":"teacher_prompt"}',
            },
        )
    makeup_rows: list[JsonValue] = [
        {
            "student_id": fixture.student_ids[name],
            "attendance": "present",
            "payload_json": '{"source":"teacher_prompt"}',
        }
        for name in makeups
    ]
    result_rows: list[JsonValue] = []
    for index, row in enumerate(student_rows):
        assert isinstance(row, dict)
        result_rows.append(
            {
                "student_id": row["student_id"],
                "correct": 8 if index == 0 else 7,
                "total": 10,
                "pct": 80 if index == 0 else 70,
            },
        )
    payload: dict[str, JsonValue] = {
        "class_code": "alpha",
        "session_kind": "main",
        "session_date": "2026-06-16",
        "subject": "Synthetic Grammar",
        "progress": "Synthetic Unit 1",
        "homework": "Synthetic worksheet",
        "students": student_rows,
        "makeups": makeup_rows,
        "test_name": "Synthetic Quiz",
        "test_kind": "quiz",
        "results": result_rows,
    }
    return payload


def _record_class_template() -> WriteActionTemplate:
    return WriteActionTemplate(
        template_id="record-class",
        schema_version="write-action-v1",
        summary="Record a synthetic class session",
        route_id="record-class",
        table_whitelist=(
            "classes",
            "sessions",
            "student_session_records",
            "tests",
            "test_results",
        ),
        columns={
            "classes": ("id", "code"),
            "sessions": (
                "id",
                "class_id",
                "session_kind",
                "session_date",
                "subject",
                "progress",
                "homework",
            ),
            "student_session_records": (
                "id",
                "session_id",
                "student_id",
                "attendance",
                "homework_score",
                "note",
                "payload_json",
            ),
            "tests": ("id", "name", "kind"),
            "test_results": (
                "id",
                "student_id",
                "session_id",
                "test_id",
                "correct",
                "total",
                "pct",
            ),
        },
        param_schema={
            "class_code": {"type": "str", "required": True},
            "session_kind": {"type": "str", "required": True},
            "session_date": {"type": "date", "required": True},
            "subject": {"type": "str"},
            "progress": {"type": "str"},
            "homework": {"type": "str"},
            "students": {"type": "list", "required": True},
            "makeups": {"type": "list", "required": True},
            "test_name": {"type": "str", "required": True},
            "test_kind": {"type": "str", "required": True},
            "results": {"type": "list", "required": True},
        },
        steps=(
            WriteStep(
                step_id="resolve_class",
                table="classes",
                op="resolve",
                match={"code": "$class_code"},
                set={},
                depends_on=(),
                bind_result={"class_id": "id"},
            ),
            WriteStep(
                step_id="insert_session",
                table="sessions",
                op="insert",
                match={},
                set={
                    "class_id": "@class_id",
                    "session_kind": "$session_kind",
                    "session_date": "$session_date",
                    "subject": "$subject",
                    "progress": "$progress",
                    "homework": "$homework",
                },
                depends_on=("resolve_class",),
                bind_result={"session_id": "lastrowid"},
            ),
            WriteStep(
                step_id="update_trigger_stub",
                table="student_session_records",
                op="update_stub",
                match={"session_id": "@session_id", "student_id": "$students[].student_id"},
                set={
                    "attendance": "$students[].attendance",
                    "homework_score": "$students[].homework_score",
                    "note": "$students[].note",
                    "payload_json": "$students[].payload_json",
                },
                depends_on=("insert_session",),
                bind_result={},
            ),
            WriteStep(
                step_id="insert_makeup_record",
                table="student_session_records",
                op="insert",
                match={},
                set={
                    "session_id": "@session_id",
                    "student_id": "$makeups[].student_id",
                    "attendance": "$makeups[].attendance",
                    "payload_json": "$makeups[].payload_json",
                },
                depends_on=("insert_session",),
                bind_result={},
            ),
            WriteStep(
                step_id="ensure_test",
                table="tests",
                op="ensure",
                match={"name": "$test_name"},
                set={"name": "$test_name", "kind": "$test_kind"},
                depends_on=(),
                bind_result={"test_id": "id"},
            ),
            WriteStep(
                step_id="insert_test_result",
                table="test_results",
                op="insert",
                match={},
                set={
                    "student_id": "$results[].student_id",
                    "session_id": "@session_id",
                    "test_id": "@test_id",
                    "correct": "$results[].correct",
                    "total": "$results[].total",
                    "pct": "$results[].pct",
                },
                depends_on=("insert_session", "ensure_test"),
                bind_result={},
            ),
        ),
        source="repo",
    )


def _failing_template() -> WriteActionTemplate:
    good = _record_class_template()
    return WriteActionTemplate(
        template_id=good.template_id,
        schema_version=good.schema_version,
        summary=good.summary,
        route_id=good.route_id,
        table_whitelist=good.table_whitelist,
        columns=good.columns,
        param_schema=good.param_schema,
        steps=(
            good.steps[0],
            good.steps[1],
            WriteStep(
                step_id="insert_bad_result",
                table="test_results",
                op="insert",
                match={},
                set={
                    "student_id": "$students[].student_id",
                    "session_id": "@session_id",
                    "test_id": "='999999'",
                    "correct": "='1'",
                    "total": "='1'",
                    "pct": "='100'",
                },
                depends_on=("insert_session",),
                bind_result={},
            ),
        ),
        source=good.source,
    )


def _student_lookup_template() -> WriteActionTemplate:
    return WriteActionTemplate(
        template_id="student-lookup",
        schema_version="write-action-v1",
        summary="Resolve one synthetic student",
        route_id="student-lookup",
        table_whitelist=("students",),
        columns={"students": ("id", "canonical_name")},
        param_schema={"student_name": {"type": "str", "required": True}},
        steps=(
            WriteStep(
                step_id="resolve_student",
                table="students",
                op="resolve",
                match={"canonical_name": "$student_name"},
                set={},
                depends_on=(),
                bind_result={"student_id": "id"},
            ),
        ),
        source="repo",
    )


def _table_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        return {
            table: _select_scalar_int(conn, f"SELECT count(*) FROM {table}", ())  # noqa: S608
            for table in TABLES
        }


def _select_scalar_int(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[int | str, ...],
) -> int:
    row = cast("tuple[int]", conn.execute(sql, params).fetchone())
    return row[0]


def _select_scalar_str(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[int | str, ...],
) -> str:
    row = cast("tuple[str]", conn.execute(sql, params).fetchone())
    return row[0]


def _row_str(row: sqlite3.Row, key: str) -> str:
    return cast("str", row[key])


def _json_source(text: str) -> str:
    payload = cast("dict[str, JsonValue]", json.loads(text))
    source = payload["source"]
    assert isinstance(source, str)
    return source


def _db_dump(db_path: Path) -> tuple[str, ...]:
    with sqlite3.connect(db_path) as conn:
        return tuple(conn.iterdump())


def _json_records(path: Path) -> list[dict[str, JsonValue]]:
    return [
        cast("dict[str, JsonValue]", json.loads(record_path.read_text(encoding="utf-8")))
        for record_path in sorted(path.glob("*.json"))
    ]
