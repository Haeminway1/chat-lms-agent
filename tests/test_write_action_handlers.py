from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from chat_lms_agent import approvals
from chat_lms_agent.approval_handlers import handle_approval
from chat_lms_agent.state import ProfileState
from chat_lms_agent.write_action_handlers import handle_write_action

if TYPE_CHECKING:
    import pytest
    from _pytest.capture import CaptureFixture

    from chat_lms_agent.state import JsonValue
    from chat_lms_agent.write_actions import WriteActionTemplate
    from chat_lms_agent.write_engine import ConnectFn


@dataclass(frozen=True, slots=True)
class DbFixture:
    profile_root: Path
    db_path: Path
    connect: ConnectRecorder


@dataclass(frozen=True, slots=True)
class ConnectRecorder:
    calls: list[Path] = field(default_factory=list)

    def __call__(self, db_path: str | Path) -> sqlite3.Connection:
        """Open a tracked SQLite connection for handler apply tests."""
        path = Path(db_path)
        self.calls.append(path)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn


@dataclass(frozen=True, slots=True)
class NonTtyStream:
    """Stand-in for an agent shell without an interactive approval terminal."""

    def isatty(self) -> bool:
        """Report that approval is not running in a teacher terminal."""
        return False

    def readline(self) -> str:
        """Return no typed confirmation because non-TTY approval is blocked first."""
        return ""


def test_write_action_cli_list_dispatch_reaches_handler(tmp_path: Path) -> None:
    # Given: a profile-scoped write-action template.
    _write_template(tmp_path, _template_payload("daily"))

    # When: the public CLI lists write-actions.
    result = _run_cli("write-action", "list", "--profile-root", str(tmp_path), "--json")

    # Then: parser and top-level dispatch reach the new handler.
    assert result.returncode == 0
    payload = _json_object(result.stdout)
    templates = _json_list(payload["templates"])
    assert payload["status"] == "PASS"
    assert templates[0]["id"] == "daily"


def test_write_action_cli_roster_dispatch_reaches_handler(tmp_path: Path) -> None:
    # Given: a synthetic profile database with active and inactive enrollments.
    fixture = _roster_db_fixture(tmp_path)

    # When: the public CLI resolves the roster.
    result = _run_cli(
        "write-action",
        "roster",
        "--class-code",
        "alpha",
        "--profile-root",
        str(fixture.profile_root),
        "--json",
    )

    # Then: parser and top-level dispatch reach the roster handler.
    payload = _json_object(result.stdout)
    assert result.returncode == 0
    assert payload["status"] == "PASS"
    assert payload["class_id"] == 1
    assert _json_list(payload["students"]) == [
        {"canonical_name": "Fictional Ada", "id": 1},
        {"canonical_name": "Fictional Ben", "id": 2},
    ]


def test_write_action_cli_session_gaps_dispatch_reaches_handler(tmp_path: Path) -> None:
    # Given: a synthetic profile database with a fully recorded class session.
    fixture = _session_gaps_db_fixture(tmp_path)
    _record_session_attendance(fixture.db_path, student_ids=(1, 2, 3, 4))

    # When: the public CLI checks session coverage gaps.
    result = _run_cli(
        "write-action",
        "session-gaps",
        "--class-code",
        "alpha",
        "--session-date",
        "2026-06-16",
        "--profile-root",
        str(fixture.profile_root),
        "--json",
    )

    # Then: parser and top-level dispatch reach the read-only handler.
    payload = _json_object(result.stdout)
    assert result.returncode == 0
    assert payload["status"] == "PASS"
    assert payload["session_id"] == 1
    assert payload["session_exists"] is True
    assert payload["total_enrolled"] == 4
    assert payload["recorded"] == 4
    assert payload["missing"] == []


def test_write_action_roster_returns_active_enrollees_without_writes(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a synthetic profile database with an active roster.
    fixture = _roster_db_fixture(tmp_path)
    before_dump = _db_dump(fixture.db_path)

    # When: roster resolves student IDs for the class code.
    exit_code = handle_write_action(
        [
            "write-action",
            "roster",
            "--profile-root",
            str(fixture.profile_root),
            "--class-code",
            "alpha",
            "--json",
        ],
        _repo_root(),
    )

    # Then: only active enrollments are returned and the database is byte-identical.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {
        "class_id": 1,
        "status": "PASS",
        "students": [
            {"canonical_name": "Fictional Ada", "id": 1},
            {"canonical_name": "Fictional Ben", "id": 2},
        ],
    }
    assert _db_dump(fixture.db_path) == before_dump


def test_write_action_roster_filters_ended_enrollments_for_session_date(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: one enrollment is still marked active but ended before the requested class date.
    fixture = _roster_db_fixture(tmp_path)

    # When: roster resolves student IDs for the class date.
    exit_code = handle_write_action(
        [
            "write-action",
            "roster",
            "--profile-root",
            str(fixture.profile_root),
            "--class-code",
            "alpha",
            "--session-date",
            "2026-06-16",
            "--json",
        ],
        _repo_root(),
    )

    # Then: stale active historical enrollments are not returned.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {
        "class_id": 1,
        "status": "PASS",
        "students": [
            {"canonical_name": "Fictional Ada", "id": 1},
            {"canonical_name": "Fictional Ben", "id": 2},
        ],
    }


def test_write_action_roster_unknown_class_returns_typed_error(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a synthetic profile database without the requested class code.
    fixture = _roster_db_fixture(tmp_path)
    before_dump = _db_dump(fixture.db_path)

    # When: roster is asked for an unknown class code.
    exit_code = handle_write_action(
        [
            "write-action",
            "roster",
            "--profile-root",
            str(fixture.profile_root),
            "--class-code",
            "missing",
            "--json",
        ],
        _repo_root(),
    )

    # Then: the command fails with UNKNOWN_CLASS and still performs no writes.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 2
    assert payload == {"error_code": "UNKNOWN_CLASS", "status": "ERROR"}
    assert _db_dump(fixture.db_path) == before_dump


def test_write_action_session_gaps_reports_partial_null_attendance_stubs(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: four active enrollees and a triggered session with two attendance updates.
    fixture = _session_gaps_db_fixture(tmp_path)
    _record_session_attendance(fixture.db_path, student_ids=(1, 3))

    # When: session-gaps checks the class/date coverage.
    exit_code = handle_write_action(
        [
            "write-action",
            "session-gaps",
            "--profile-root",
            str(fixture.profile_root),
            "--class-code",
            "alpha",
            "--session-date",
            "2026-06-16",
            "--json",
        ],
        _repo_root(),
    )

    # Then: the two NULL-attendance stubs are reported as missing.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {
        "missing": [{"student_id": 2}, {"student_id": 4}],
        "recorded": 2,
        "session_exists": True,
        "session_id": 1,
        "status": "PASS",
        "total_enrolled": 4,
    }


def test_write_action_session_gaps_reports_full_coverage(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: four active enrollees and every triggered stub has attendance.
    fixture = _session_gaps_db_fixture(tmp_path)
    _record_session_attendance(fixture.db_path, student_ids=(1, 2, 3, 4))

    # When: session-gaps checks the class/date coverage.
    exit_code = handle_write_action(
        [
            "write-action",
            "session-gaps",
            "--profile-root",
            str(fixture.profile_root),
            "--class-code",
            "alpha",
            "--session-date",
            "2026-06-16",
            "--json",
        ],
        _repo_root(),
    )

    # Then: no missing NULL-attendance stubs remain.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {
        "missing": [],
        "recorded": 4,
        "session_exists": True,
        "session_id": 1,
        "status": "PASS",
        "total_enrolled": 4,
    }


def test_write_action_session_gaps_ignores_ended_active_enrollments(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: the DB contains a stale active enrollment and even a stale attendance stub.
    fixture = _session_gaps_db_fixture(tmp_path)
    _record_session_attendance(fixture.db_path, student_ids=(1, 2, 3, 4, 5))

    # When: session-gaps checks coverage for the class date.
    exit_code = handle_write_action(
        [
            "write-action",
            "session-gaps",
            "--profile-root",
            str(fixture.profile_root),
            "--class-code",
            "alpha",
            "--session-date",
            "2026-06-16",
            "--json",
        ],
        _repo_root(),
    )

    # Then: total, recorded, and missing are based on date-active enrollment only.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {
        "missing": [],
        "recorded": 4,
        "session_exists": True,
        "session_id": 1,
        "status": "PASS",
        "total_enrolled": 4,
    }


def test_write_action_session_gaps_passes_when_session_is_absent(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a class exists, but the requested date has no session row.
    fixture = _session_gaps_db_fixture(tmp_path)

    # When: session-gaps checks an absent date.
    exit_code = handle_write_action(
        [
            "write-action",
            "session-gaps",
            "--profile-root",
            str(fixture.profile_root),
            "--class-code",
            "alpha",
            "--session-date",
            "2026-06-17",
            "--json",
        ],
        _repo_root(),
    )

    # Then: no session is treated as a passing no-op read.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {
        "missing": [],
        "note": "no session for that date",
        "session_exists": False,
        "session_id": None,
        "status": "PASS",
    }


def test_write_action_session_gaps_unknown_class_returns_typed_error(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: no class exists for the requested code.
    fixture = _session_gaps_db_fixture(tmp_path)

    # When: session-gaps is asked for an unknown class.
    exit_code = handle_write_action(
        [
            "write-action",
            "session-gaps",
            "--profile-root",
            str(fixture.profile_root),
            "--class-code",
            "missing",
            "--session-date",
            "2026-06-16",
            "--json",
        ],
        _repo_root(),
    )

    # Then: the same UNKNOWN_CLASS boundary as roster is returned.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 2
    assert payload == {"error_code": "UNKNOWN_CLASS", "status": "ERROR"}


def test_write_action_session_gaps_performs_no_writes(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a partial session coverage database.
    fixture = _session_gaps_db_fixture(tmp_path)
    _record_session_attendance(fixture.db_path, student_ids=(1, 3))
    before_dump = _db_dump(fixture.db_path)

    # When: session-gaps reads coverage.
    exit_code = handle_write_action(
        [
            "write-action",
            "session-gaps",
            "--profile-root",
            str(fixture.profile_root),
            "--class-code",
            "alpha",
            "--session-date",
            "2026-06-16",
            "--json",
        ],
        _repo_root(),
    )

    # Then: it reports gaps without mutating the SQLite database.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["missing"] == [{"student_id": 2}, {"student_id": 4}]
    assert _db_dump(fixture.db_path) == before_dump


def test_write_action_index_check_reports_states_conflicts_and_readonly(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: declared backing indexes covering present, missing, and absent tables.
    fixture = _index_check_db_fixture(tmp_path)
    _write_template(fixture.profile_root, _index_check_template_payload())
    before_dump = _db_dump(fixture.db_path)

    # When: index --check inspects the profile database.
    exit_code = handle_write_action(
        [
            "write-action",
            "index",
            "--check",
            "--profile-root",
            str(fixture.profile_root),
            "--json",
        ],
        _repo_root(),
    )

    # Then: it reports index state and duplicate groups without changing the DB.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["db_present"] is True
    states = {
        item["table"]: item
        for item in _json_list(payload["indexes"])
        if isinstance(item, dict)
    }
    assert states["present_rows"] == {
        "columns": ["class_id", "session_date"],
        "state": "PRESENT",
        "table": "present_rows",
    }
    assert states["missing_rows"] == {
        "columns": ["class_id", "session_date"],
        "state": "MISSING",
        "table": "missing_rows",
    }
    assert states["absent_rows"] == {
        "columns": ["class_id", "session_date"],
        "state": "TABLE_ABSENT",
        "table": "absent_rows",
    }
    assert _json_list(payload["conflicts"]) == [
        {
            "columns": ["class_id", "session_date"],
            "row_groups": [
                {
                    "count": 2,
                    "key": {"class_id": 1, "session_date": "2026-06-16"},
                    "rowids": [1, 2],
                },
            ],
            "table": "missing_rows",
        },
    ]
    assert _db_dump(fixture.db_path) == before_dump


def test_write_action_cli_index_check_dispatch_reaches_handler(tmp_path: Path) -> None:
    # Given: a profile with one declared, present backing index.
    fixture = _index_check_db_fixture(tmp_path)
    _write_template(
        fixture.profile_root,
        {
            **_index_check_template_payload(),
            "indexes": {"present_rows": [["class_id", "session_date"]]},
        },
    )

    # When: the public CLI dispatches index --check.
    result = _run_cli(
        "write-action",
        "index",
        "--check",
        "--profile-root",
        str(fixture.profile_root),
        "--json",
    )

    # Then: parser and top-level dispatch reach the handler.
    payload = _json_object(result.stdout)
    assert result.returncode == 0
    assert payload["status"] == "PASS"
    assert {
        "columns": ["class_id", "session_date"],
        "state": "PRESENT",
        "table": "present_rows",
    } in _json_list(payload["indexes"])


def test_write_action_index_check_missing_db_returns_db_unavailable(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: index declarations but no profile database file.
    _write_template(tmp_path, _index_check_template_payload())

    # When: index --check cannot open the read-only database.
    exit_code = handle_write_action(
        ["write-action", "index", "--check", "--profile-root", str(tmp_path), "--json"],
        _repo_root(),
    )

    # Then: the failure is typed and still has no write side effect.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 2
    assert payload == {
        "db_present": False,
        "error_code": "DB_UNAVAILABLE",
        "status": "ERROR",
    }


def test_write_action_index_apply_creates_unique_index_and_backup(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a declared index with no duplicate rows yet.
    fixture = _index_check_db_fixture(tmp_path)
    with sqlite3.connect(fixture.db_path) as conn:
        _ = conn.execute("DELETE FROM missing_rows WHERE id = 2")
        conn.commit()
    _write_template(
        fixture.profile_root,
        {
            **_index_check_template_payload(),
            "indexes": {"missing_rows": [["class_id", "session_date"]]},
        },
    )

    # When: index --apply creates the backing UNIQUE index.
    exit_code = handle_write_action(
        ["write-action", "index", "--apply", "--profile-root", str(fixture.profile_root), "--json"],
        tmp_path / "empty-repo",
    )

    # Then: the index is created transactionally and a pre-change backup remains.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["applied"] == [
        {
            "columns": ["class_id", "session_date"],
            "index_name": "ux_missing_rows_class_id_session_date",
            "table": "missing_rows",
        },
    ]
    backup = Path(str(payload["backup"]))
    assert backup.exists()
    with sqlite3.connect(fixture.db_path) as conn:
        conn.row_factory = sqlite3.Row
        indexes = conn.execute(
            "SELECT name FROM pragma_index_list('missing_rows') WHERE \"unique\" = 1",
        ).fetchall()
    assert [row["name"] for row in indexes] == ["ux_missing_rows_class_id_session_date"]


def test_write_action_index_apply_duplicate_rows_rolls_back_with_conflicts(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a declared unique index whose table already has duplicate natural keys.
    fixture = _index_check_db_fixture(tmp_path)
    _write_template(
        fixture.profile_root,
        {
            **_index_check_template_payload(),
            "indexes": {"missing_rows": [["class_id", "session_date"]]},
        },
    )
    before_dump = _db_dump(fixture.db_path)

    # When: index --apply attempts to build the UNIQUE index.
    exit_code = handle_write_action(
        ["write-action", "index", "--apply", "--profile-root", str(fixture.profile_root), "--json"],
        tmp_path / "empty-repo",
    )

    # Then: it reports conflicts, rolls back, and keeps the backup.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "INDEX_BUILD_CONFLICT"
    assert payload["conflict"] == {
        "columns": ["class_id", "session_date"],
        "row_groups": [
            {
                "count": 2,
                "key": {"class_id": 1, "session_date": "2026-06-16"},
                "rowids": [1, 2],
            },
        ],
        "table": "missing_rows",
    }
    assert Path(str(payload["backup"])).exists()
    assert _db_dump(fixture.db_path) == before_dump
    with sqlite3.connect(fixture.db_path) as conn:
        unique_indexes = conn.execute(
            "SELECT name FROM pragma_index_list('missing_rows') WHERE \"unique\" = 1",
        ).fetchall()
    assert unique_indexes == []


def test_write_action_index_apply_uses_hash_suffix_when_index_name_collides(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: the preferred generated index name already exists for a different shape.
    fixture = _index_check_db_fixture(tmp_path)
    with sqlite3.connect(fixture.db_path) as conn:
        _ = conn.execute("DELETE FROM missing_rows WHERE id = 2")
        _ = conn.execute("CREATE INDEX ux_missing_rows_class_id_session_date ON missing_rows(id)")
        conn.commit()
    _write_template(
        fixture.profile_root,
        {
            **_index_check_template_payload(),
            "indexes": {"missing_rows": [["class_id", "session_date"]]},
        },
    )

    # When: index --apply cannot use the preferred name.
    exit_code = handle_write_action(
        ["write-action", "index", "--apply", "--profile-root", str(fixture.profile_root), "--json"],
        tmp_path / "empty-repo",
    )

    # Then: it creates a deterministic safe fallback name instead of no-oping.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    applied = _json_list(payload["applied"])
    assert len(applied) == 1
    applied_item = applied[0]
    assert isinstance(applied_item, dict)
    index_name = applied_item["index_name"]
    assert isinstance(index_name, str)
    assert index_name.startswith("ux_missing_rows_class_id_session_date_")
    with sqlite3.connect(fixture.db_path) as conn:
        conn.row_factory = sqlite3.Row
        indexes = conn.execute(
            "SELECT name FROM pragma_index_list('missing_rows') WHERE \"unique\" = 1",
        ).fetchall()
    assert [row["name"] for row in indexes] == [index_name]


def test_write_action_index_apply_does_not_noop_on_same_name_non_unique_index(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: the preferred name exists with the same columns, but it is not UNIQUE.
    fixture = _index_check_db_fixture(tmp_path)
    with sqlite3.connect(fixture.db_path) as conn:
        _ = conn.execute("DELETE FROM missing_rows WHERE id = 2")
        _ = conn.execute(
            "CREATE INDEX ux_missing_rows_class_id_session_date "
            "ON missing_rows(class_id, session_date)",
        )
        conn.commit()
    _write_template(
        fixture.profile_root,
        {
            **_index_check_template_payload(),
            "indexes": {"missing_rows": [["class_id", "session_date"]]},
        },
    )

    # When: index --apply ensures the declared full UNIQUE invariant.
    exit_code = handle_write_action(
        ["write-action", "index", "--apply", "--profile-root", str(fixture.profile_root), "--json"],
        tmp_path / "empty-repo",
    )

    # Then: it does not no-op on the existing non-unique index.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    applied = _json_list(payload["applied"])
    applied_item = applied[0]
    assert isinstance(applied_item, dict)
    index_name = applied_item["index_name"]
    assert isinstance(index_name, str)
    assert index_name.startswith("ux_missing_rows_class_id_session_date_")
    with sqlite3.connect(fixture.db_path) as conn:
        conn.row_factory = sqlite3.Row
        unique_indexes = conn.execute(
            "SELECT name FROM pragma_index_list('missing_rows') "
            'WHERE "unique" = 1 AND partial = 0',
        ).fetchall()
    assert [row["name"] for row in unique_indexes] == [index_name]


def test_write_action_list_explain_and_unknown_template(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    # Given: a seeded profile template.
    _write_template(tmp_path, _template_payload("daily"))

    # When: list, explain, and missing-template explain are invoked.
    list_exit = handle_write_action(
        ["write-action", "list", "--profile-root", str(tmp_path), "--json"],
        _repo_root(),
    )
    explain_exit = handle_write_action(
        [
            "write-action",
            "explain",
            "--profile-root",
            str(tmp_path),
            "--id",
            "daily",
            "--json",
        ],
        _repo_root(),
    )
    unknown_exit = handle_write_action(
        [
            "write-action",
            "explain",
            "--profile-root",
            str(tmp_path),
            "--id",
            "missing",
            "--json",
        ],
        _repo_root(),
    )

    # Then: template metadata and schema are visible, while unknown ids are typed errors.
    stdout_lines = capsys.readouterr().out.splitlines()
    list_payload = _json_object(stdout_lines[0])
    explain_payload = _json_object(stdout_lines[1])
    unknown_payload = _json_object(stdout_lines[2])
    assert [list_exit, explain_exit, unknown_exit] == [0, 0, 2]
    assert _json_list(list_payload["templates"])[0] == {
        "id": "daily",
        "route_id": "daily-route",
        "source": "profile",
        "summary": "Record a synthetic session",
    }
    assert explain_payload["status"] == "PASS"
    assert explain_payload["id"] == "daily"
    assert explain_payload["table_whitelist"] == ["classes", "sessions"]
    assert explain_payload["columns"] == {"classes": ["id", "code"], "sessions": ["id", "class_id"]}
    assert explain_payload["param_schema"] == {
        "class_code": {"required": True, "type": "str"},
    }
    assert _json_list(explain_payload["steps"]) == [
        {"op": "resolve", "step_id": "resolve_class", "table": "classes"},
        {"op": "insert", "step_id": "insert_session", "table": "sessions"},
    ]
    assert unknown_payload == {"error_code": "UNKNOWN_TEMPLATE", "status": "ERROR"}


def test_write_action_plan_is_dry_run_and_reports_plan_error(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    # Given: one valid template and payload files.
    _write_template(tmp_path, _template_payload("daily"))
    valid_payload = tmp_path / "valid-payload.json"
    missing_payload = tmp_path / "missing-payload.json"
    _write_json(valid_payload, {"class_code": "alpha"})
    _write_json(missing_payload, {})

    # When: plan runs with valid and invalid payloads.
    valid_exit = handle_write_action(
        [
            "write-action",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--id",
            "daily",
            "--from",
            str(valid_payload),
            "--json",
        ],
        _repo_root(),
    )
    missing_exit = handle_write_action(
        [
            "write-action",
            "plan",
            "--profile-root",
            str(tmp_path),
            "--id",
            "daily",
            "--from",
            str(missing_payload),
            "--json",
        ],
        _repo_root(),
    )

    # Then: the dry-run reports compiled statements and never creates a DB.
    stdout_lines = capsys.readouterr().out.splitlines()
    valid = _json_object(stdout_lines[0])
    missing = _json_object(stdout_lines[1])
    assert [valid_exit, missing_exit] == [0, 2]
    assert valid["status"] == "PASS"
    assert valid["dry_run"] is True
    assert valid["statement_count"] == 2
    assert _json_list(valid["steps"]) == [
        {"op": "resolve", "predicted_write": False, "step_id": "resolve_class", "table": "classes"},
        {"op": "insert", "predicted_write": True, "step_id": "insert_session", "table": "sessions"},
    ]
    assert missing["status"] == "ERROR"
    assert missing["error_code"] == "INVALID_PARAMS"
    assert "MISSING_PARAM: class_code" in _json_list(missing["errors"])
    assert not (tmp_path / "data" / "chat_lms.db").exists()


def test_write_action_apply_uses_injected_connect_and_returns_engine_success(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a registered template, payload, and synthetic database under the profile data root.
    fixture = _db_fixture(tmp_path)
    _write_template(tmp_path, _template_payload("daily"))
    _approve_registration(fixture.profile_root, "daily")
    payload_path = tmp_path / "payload.json"
    _write_json(payload_path, {"class_code": "alpha"})

    # When: apply runs through the injected connection seam.
    exit_code = handle_write_action(
        [
            "write-action",
            "apply",
            "--profile-root",
            str(fixture.profile_root),
            "--id",
            "daily",
            "--from",
            str(payload_path),
            "--json",
        ],
        _repo_root(),
        connect=fixture.connect,
    )

    # Then: the engine payload is returned verbatim and the row lands in SQLite.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["rows_affected"] == 1
    assert fixture.connect.calls == [fixture.db_path.resolve()]
    with sqlite3.connect(fixture.db_path) as conn:
        rows = conn.execute(
            "SELECT class_id FROM sessions ORDER BY id",
        ).fetchall()
    assert rows == [(1,)]


def test_write_action_apply_unregistered_template_needs_approval_without_engine_call(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a valid template, payload, and database that have not crossed registration approval.
    fixture = _db_fixture(tmp_path)
    _write_template(tmp_path, _template_payload("daily"))
    payload_path = tmp_path / "payload.json"
    _write_json(payload_path, {"class_code": "alpha"})
    before_dump = _db_dump(fixture.db_path)

    # When: apply is attempted before registration approval.
    exit_code = handle_write_action(
        [
            "write-action",
            "apply",
            "--profile-root",
            str(fixture.profile_root),
            "--id",
            "daily",
            "--from",
            str(payload_path),
            "--json",
        ],
        _repo_root(),
        connect=fixture.connect,
    )

    # Then: the trust boundary blocks replay before the engine or DB write.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 3
    assert payload["status"] == "NEEDS_APPROVAL"
    assert payload["error_code"] == "TEMPLATE_NOT_REGISTERED"
    assert payload["template_id"] == "daily"
    assert "write-action register --id <id>" in str(payload["hint"])
    assert fixture.connect.calls == []
    assert _db_dump(fixture.db_path) == before_dump


def test_write_action_register_valid_template_creates_planned_approval(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a valid write-action template that has not been registered.
    _write_template(tmp_path, _template_payload("daily"))

    # When: register is requested.
    exit_code = handle_write_action(
        [
            "write-action",
            "register",
            "--profile-root",
            str(tmp_path),
            "--id",
            "daily",
            "--json",
        ],
        _repo_root(),
    )

    # Then: a persistent approval request is planned for teacher approval.
    payload = _json_object(capsys.readouterr().out)
    approval_id = payload["approval_id"]
    assert exit_code == 3
    assert payload["status"] == "NEEDS_APPROVAL"
    assert payload["template_id"] == "daily"
    assert isinstance(approval_id, str)
    assert approval_id == approvals.approval_id_for("write-action:daily")
    assert "approval approve --id" in str(payload["hint"])
    assert not approvals.approval_is_approved(
        _profile_state(tmp_path),
        approval_id,
        "write-action:daily",
    )
    list_exit, list_payload = approvals.show_approval(_profile_state(tmp_path), approval_id)
    assert list_exit == 0
    assert list_payload["approval_status"] == "PLANNED"


def test_write_action_register_unknown_template_returns_typed_error(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: no matching template exists.
    _write_template(tmp_path, _template_payload("daily"))

    # When: register is requested for a missing template id.
    exit_code = handle_write_action(
        [
            "write-action",
            "register",
            "--profile-root",
            str(tmp_path),
            "--id",
            "missing",
            "--json",
        ],
        _repo_root(),
    )

    # Then: the command fails before creating any approval request.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 2
    assert payload == {"error_code": "UNKNOWN_TEMPLATE", "status": "ERROR"}
    assert approvals.pending_approval_ids(_profile_state(tmp_path)) == []


def test_write_action_register_then_teacher_approval_unlocks_apply(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a valid template, payload, and synthetic database under the profile root.
    fixture = _db_fixture(tmp_path)
    _write_template(tmp_path, _template_payload("daily"))
    payload_path = tmp_path / "payload.json"
    _write_json(payload_path, {"class_code": "alpha"})

    # When: registration is planned, the teacher approval state is simulated, and apply runs.
    register_exit = handle_write_action(
        [
            "write-action",
            "register",
            "--profile-root",
            str(fixture.profile_root),
            "--id",
            "daily",
            "--json",
        ],
        _repo_root(),
    )
    register_payload = _json_object(capsys.readouterr().out)
    approval_id = register_payload["approval_id"]
    assert isinstance(approval_id, str)
    approve_exit, approve_payload = approvals.approve_request(
        _profile_state(fixture.profile_root),
        approval_id,
        "teacher",
    )
    apply_exit = handle_write_action(
        [
            "write-action",
            "apply",
            "--profile-root",
            str(fixture.profile_root),
            "--id",
            "daily",
            "--from",
            str(payload_path),
            "--json",
        ],
        _repo_root(),
        connect=fixture.connect,
    )

    # Then: approved registration persists and replay writes through the engine.
    apply_payload = _json_object(capsys.readouterr().out)
    assert register_exit == 3
    assert approve_exit == 0
    assert approve_payload["approval_status"] == "APPROVED"
    assert apply_exit == 0
    assert apply_payload["status"] == "PASS"
    assert apply_payload["rows_affected"] == 1
    assert fixture.connect.calls == [fixture.db_path.resolve()]
    with sqlite3.connect(fixture.db_path) as conn:
        assert conn.execute("SELECT count(*) FROM sessions").fetchone()[0] == 1


def test_write_action_register_already_approved_returns_pass(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: the template registration approval is already approved.
    _write_template(tmp_path, _template_payload("daily"))
    approval_id = _approve_registration(tmp_path, "daily")

    # When: registration is requested again.
    exit_code = handle_write_action(
        [
            "write-action",
            "register",
            "--profile-root",
            str(tmp_path),
            "--id",
            "daily",
            "--json",
        ],
        _repo_root(),
    )

    # Then: the command reports the persistent active registration without consuming it.
    payload = _json_object(capsys.readouterr().out)
    assert exit_code == 0
    assert payload == {"already_registered": True, "status": "PASS", "template_id": "daily"}
    assert approvals.approval_is_approved(
        _profile_state(tmp_path),
        approval_id,
        "write-action:daily",
    )


def test_write_action_registration_uses_existing_real_approval_gate(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    # Given: a planned registration approval created by write-action register.
    _write_template(tmp_path, _template_payload("daily"))
    register_exit = handle_write_action(
        [
            "write-action",
            "register",
            "--profile-root",
            str(tmp_path),
            "--id",
            "daily",
            "--json",
        ],
        _repo_root(),
    )
    approval_id = _json_object(capsys.readouterr().out)["approval_id"]
    assert isinstance(approval_id, str)

    # When: an agent-like non-TTY stream and the agent actor try to approve it.
    non_tty_exit = handle_approval(
        [
            "approval",
            "approve",
            "--profile-root",
            str(tmp_path),
            "--id",
            approval_id,
            "--actor",
            "teacher",
            "--json",
        ],
        _repo_root(),
        stdin=NonTtyStream(),
    )
    self_approval_exit, self_approval_payload = approvals.approve_request(
        _profile_state(tmp_path),
        approval_id,
        approvals.AGENT_ACTOR,
    )

    # Then: the existing TTY gate and actor self-rejection both remain intact.
    non_tty_payload = _json_object(capsys.readouterr().out)
    assert register_exit == 3
    assert non_tty_exit == 5
    assert non_tty_payload["status"] == "BLOCKED"
    assert non_tty_payload["error_code"] == "APPROVAL_REQUIRES_INTERACTIVE"
    assert self_approval_exit == 2
    assert self_approval_payload["error_code"] == "SELF_APPROVAL_REJECTED"


def test_write_action_apply_maps_engine_unsafe_and_error(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: approved registrations and payloads that force engine ERROR and UNSAFE outcomes.
    error_root = tmp_path / "error-profile"
    unsafe_root = tmp_path / "unsafe-profile"
    _write_template(error_root, _template_payload("daily"))
    _write_template(unsafe_root, _template_payload("daily"))
    _approve_registration(error_root, "daily")
    _approve_registration(unsafe_root, "daily")
    _write_json(error_root / "payload.json", {})
    _write_json(unsafe_root / "payload.json", {"class_code": "alpha"})

    def unsafe_engine(
        profile: ProfileState,
        template: WriteActionTemplate,
        params: dict[str, JsonValue],
        *,
        db_path: str | Path,
        connect: ConnectFn,
    ) -> tuple[int, dict[str, JsonValue]]:
        _ = (profile, template, params, db_path, connect)
        return 4, {"status": "UNSAFE", "error_code": "DB_PATH_OUT_OF_PROFILE"}

    # When: apply reaches the engine's compile and pinning failures.
    error_exit = handle_write_action(
        [
            "write-action",
            "apply",
            "--profile-root",
            str(error_root),
            "--id",
            "daily",
            "--from",
            str(error_root / "payload.json"),
            "--json",
        ],
        _repo_root(),
        connect=ConnectRecorder(),
    )
    unsafe_connect = ConnectRecorder()
    monkeypatch.setattr("chat_lms_agent.write_action_handlers.run_write_action", unsafe_engine)
    unsafe_exit = handle_write_action(
        [
            "write-action",
            "apply",
            "--profile-root",
            str(unsafe_root),
            "--id",
            "daily",
            "--from",
            str(unsafe_root / "payload.json"),
            "--json",
        ],
        _repo_root(),
        connect=unsafe_connect,
    )

    # Then: CLI returns engine exit codes 2 and 4 without remapping.
    stdout_lines = capsys.readouterr().out.splitlines()
    error_payload = _json_object(stdout_lines[0])
    unsafe_payload = _json_object(stdout_lines[1])
    assert error_exit == 2
    assert error_payload["status"] == "ERROR"
    assert error_payload["error_code"] == "INVALID_PARAMS"
    assert unsafe_exit == 4
    assert unsafe_payload == {"error_code": "DB_PATH_OUT_OF_PROFILE", "status": "UNSAFE"}
    assert unsafe_connect.calls == []


def test_write_action_invalid_payload_files_return_typed_error(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    # Given: missing, malformed, and non-object payload sources.
    _write_template(tmp_path, _template_payload("daily"))
    invalid_json = tmp_path / "invalid.json"
    list_json = tmp_path / "list.json"
    invalid_json.write_text("{not json", encoding="utf-8")
    _write_json(list_json, ["not", "an", "object"])

    # When: plan attempts to load each invalid payload.
    missing_exit = _plan_from(tmp_path, tmp_path / "missing.json")
    invalid_exit = _plan_from(tmp_path, invalid_json)
    list_exit = _plan_from(tmp_path, list_json)

    # Then: all payload boundary failures use INVALID_PAYLOAD.
    payloads = [_json_object(line) for line in capsys.readouterr().out.splitlines()]
    assert [missing_exit, invalid_exit, list_exit] == [2, 2, 2]
    assert payloads == [
        {"error_code": "INVALID_PAYLOAD", "status": "ERROR"},
        {"error_code": "INVALID_PAYLOAD", "status": "ERROR"},
        {"error_code": "INVALID_PAYLOAD", "status": "ERROR"},
    ]


def test_write_action_doctor_reports_valid_and_invalid_templates(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    # Given: one valid profile and one profile with a structurally invalid template.
    valid_root = tmp_path / "valid"
    invalid_root = tmp_path / "invalid"
    _write_template(valid_root, _template_payload("daily"))
    _write_template(
        invalid_root,
        {
            **_template_payload("daily"),
            "steps": [
                {
                    "step_id": "bad_column",
                    "table": "sessions",
                    "op": "insert",
                    "set": {"unsafe_column": "$class_code"},
                },
            ],
        },
    )

    # When: doctor validates both profiles.
    valid_exit = handle_write_action(
        ["write-action", "doctor", "--profile-root", str(valid_root), "--json"],
        _repo_root(),
    )
    invalid_exit = handle_write_action(
        ["write-action", "doctor", "--profile-root", str(invalid_root), "--json"],
        _repo_root(),
    )

    # Then: valid templates pass and structural errors fail loudly.
    stdout_lines = capsys.readouterr().out.splitlines()
    valid_payload = _json_object(stdout_lines[0])
    invalid_payload = _json_object(stdout_lines[1])
    assert [valid_exit, invalid_exit] == [0, 2]
    assert valid_payload["status"] == "PASS"
    assert valid_payload["template_count"] == 3
    assert valid_payload["invalid_count"] == 0
    assert invalid_payload["status"] == "ERROR"
    assert invalid_payload["invalid_count"] == 1
    errors = _json_list(_json_list(invalid_payload["templates"])[0]["errors"])
    assert errors == ["STEP_COLUMN_NOT_WHITELISTED: bad_column.sessions.unsafe_column"]


def _plan_from(profile_root: Path, payload_path: Path) -> int:
    return handle_write_action(
        [
            "write-action",
            "plan",
            "--profile-root",
            str(profile_root),
            "--id",
            "daily",
            "--from",
            str(payload_path),
            "--json",
        ],
        _repo_root(),
    )


def _approve_registration(profile_root: Path, template_id: str) -> str:
    profile = _profile_state(profile_root)
    plan_id = f"write-action:{template_id}"
    request = approvals.ensure_approval_request(
        profile,
        plan_id=plan_id,
        operation="write-action register",
    )
    approval_id = request["approval_id"]
    assert isinstance(approval_id, str)
    code, payload = approvals.approve_request(profile, approval_id, "teacher")
    assert code == 0
    assert payload["approval_status"] == "APPROVED"
    return approval_id


def _profile_state(profile_root: Path) -> ProfileState:
    return ProfileState(root=profile_root.resolve(), repo_root=_repo_root())


def _db_fixture(tmp_path: Path) -> DbFixture:
    profile_root = tmp_path.resolve()
    db_path = profile_root / "data" / "chat_lms.db"
    _create_db(db_path)
    return DbFixture(profile_root=profile_root, db_path=db_path, connect=ConnectRecorder())


def _roster_db_fixture(tmp_path: Path) -> DbFixture:
    profile_root = tmp_path.resolve()
    db_path = profile_root / "data" / "chat_lms.db"
    _create_roster_db(db_path)
    return DbFixture(profile_root=profile_root, db_path=db_path, connect=ConnectRecorder())


def _session_gaps_db_fixture(tmp_path: Path) -> DbFixture:
    profile_root = tmp_path.resolve()
    db_path = profile_root / "data" / "chat_lms.db"
    _create_session_gaps_db(db_path)
    return DbFixture(profile_root=profile_root, db_path=db_path, connect=ConnectRecorder())


def _index_check_db_fixture(tmp_path: Path) -> DbFixture:
    profile_root = tmp_path.resolve()
    db_path = profile_root / "data" / "chat_lms.db"
    _create_index_check_db(db_path)
    return DbFixture(profile_root=profile_root, db_path=db_path, connect=ConnectRecorder())


def _create_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        _ = conn.executescript(
            """
            CREATE TABLE classes(id INTEGER PRIMARY KEY, code TEXT UNIQUE);
            CREATE TABLE sessions(id INTEGER PRIMARY KEY, class_id INTEGER);
            INSERT INTO classes(code) VALUES ('alpha');
            """,
        )


def _create_roster_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        _ = conn.executescript(
            """
            CREATE TABLE classes(id INTEGER PRIMARY KEY, code TEXT UNIQUE, canonical_name TEXT);
            CREATE TABLE students(
              id INTEGER PRIMARY KEY,
              canonical_name TEXT UNIQUE,
              active INTEGER DEFAULT 1
            );
            CREATE TABLE enrollments(
              id INTEGER PRIMARY KEY,
              student_id INTEGER,
              class_id INTEGER,
              status TEXT,
              started_on TEXT,
              ended_on TEXT
            );
            INSERT INTO classes(id, code, canonical_name)
            VALUES (1, 'alpha', 'Fictional Alpha Class');
            INSERT INTO students(id, canonical_name)
            VALUES
              (1, 'Fictional Ada'),
              (2, 'Fictional Ben'),
              (3, 'Fictional Cora'),
              (4, 'Fictional Drew');
            INSERT INTO enrollments(student_id, class_id, status, started_on, ended_on)
            VALUES
              (1, 1, 'active', NULL, NULL),
              (2, 1, 'active', NULL, NULL),
              (3, 1, 'inactive', NULL, NULL),
              (4, 1, 'active', '2026-01-01', '2026-03-01');
            """,
        )


def _create_session_gaps_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        _ = conn.executescript(
            """
            CREATE TABLE classes(id INTEGER PRIMARY KEY, code TEXT UNIQUE, canonical_name TEXT);
            CREATE TABLE students(
              id INTEGER PRIMARY KEY,
              canonical_name TEXT UNIQUE,
              active INTEGER DEFAULT 1
            );
            CREATE TABLE enrollments(
              id INTEGER PRIMARY KEY,
              student_id INTEGER,
              class_id INTEGER,
              status TEXT,
              started_on TEXT,
              ended_on TEXT
            );
            CREATE TABLE sessions(
              id INTEGER PRIMARY KEY,
              class_id INTEGER,
              session_kind TEXT DEFAULT 'main',
              session_date TEXT
            );
            CREATE TABLE student_session_records(
              id INTEGER PRIMARY KEY,
              session_id INTEGER,
              student_id INTEGER,
              attendance TEXT,
              UNIQUE(session_id, student_id)
            );
            CREATE TRIGGER trg_sessions_auto_student_session_records
            AFTER INSERT ON sessions
            WHEN NEW.session_kind IN ('main', 'clinic')
            BEGIN
              INSERT INTO student_session_records(session_id, student_id)
              SELECT NEW.id, e.student_id
              FROM enrollments e
              WHERE e.class_id = NEW.class_id AND e.status = 'active';
            END;
            INSERT INTO classes(id, code, canonical_name)
            VALUES (1, 'alpha', 'Fictional Alpha Class');
            INSERT INTO students(id, canonical_name)
            VALUES
              (1, 'Fictional Ada'),
              (2, 'Fictional Ben'),
              (3, 'Fictional Cora'),
              (4, 'Fictional Drew'),
              (5, 'Fictional Ended');
            INSERT INTO enrollments(student_id, class_id, status, started_on, ended_on)
            VALUES
              (1, 1, 'active', NULL, NULL),
              (2, 1, 'active', NULL, NULL),
              (3, 1, 'active', NULL, NULL),
              (4, 1, 'active', NULL, NULL),
              (5, 1, 'active', '2026-01-01', '2026-03-01');
            INSERT INTO sessions(id, class_id, session_kind, session_date)
            VALUES (1, 1, 'main', '2026-06-16');
            """,
        )


def _create_index_check_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        _ = conn.executescript(
            """
            CREATE TABLE present_rows(
              id INTEGER PRIMARY KEY,
              class_id INTEGER,
              session_date TEXT
            );
            CREATE UNIQUE INDEX ux_present_rows_class_date
            ON present_rows(class_id, session_date);
            CREATE TABLE missing_rows(
              id INTEGER PRIMARY KEY,
              class_id INTEGER,
              session_date TEXT
            );
            INSERT INTO missing_rows(id, class_id, session_date)
            VALUES
              (1, 1, '2026-06-16'),
              (2, 1, '2026-06-16'),
              (3, 1, '2026-06-17');
            """,
        )


def _record_session_attendance(db_path: Path, *, student_ids: tuple[int, ...]) -> None:
    with sqlite3.connect(db_path) as conn:
        for student_id in student_ids:
            _ = conn.execute(
                """
                UPDATE student_session_records
                SET attendance = 'present'
                WHERE session_id = 1 AND student_id = ?
                """,
                (student_id,),
            )
        conn.commit()


def _template_payload(template_id: str) -> dict[str, JsonValue]:
    return {
        "schema_version": "write-action-v1",
        "id": template_id,
        "summary": "Record a synthetic session",
        "route_id": "daily-route",
        "table_whitelist": ["classes", "sessions"],
        "columns": {"classes": ["id", "code"], "sessions": ["id", "class_id"]},
        "param_schema": {"class_code": {"type": "str", "required": True}},
        "steps": [
            {
                "step_id": "resolve_class",
                "table": "classes",
                "op": "resolve",
                "match": {"code": "$class_code"},
                "bind_result": {"class_id": "id"},
            },
            {
                "step_id": "insert_session",
                "table": "sessions",
                "op": "insert",
                "set": {"class_id": "@class_id"},
                "depends_on": ["resolve_class"],
                "bind_result": {"session_id": "lastrowid"},
            },
        ],
    }


def _index_check_template_payload() -> dict[str, JsonValue]:
    return {
        "schema_version": "write-action-v1",
        "id": "index-check",
        "summary": "Check declared indexes",
        "route_id": "index-check",
        "table_whitelist": ["present_rows", "missing_rows", "absent_rows"],
        "columns": {
            "present_rows": ["id", "class_id", "session_date"],
            "missing_rows": ["id", "class_id", "session_date"],
            "absent_rows": ["id", "class_id", "session_date"],
        },
        "indexes": {
            "present_rows": [["class_id", "session_date"]],
            "missing_rows": [["class_id", "session_date"]],
            "absent_rows": [["class_id", "session_date"]],
        },
        "param_schema": {},
        "steps": [],
    }


def _write_template(profile_root: Path, payload: dict[str, JsonValue]) -> None:
    _write_json(profile_root / ".chat-lms-state" / "write-actions" / "daily.json", payload)


def _write_json(path: Path, payload: JsonValue) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _json_object(value: str | JsonValue) -> dict[str, JsonValue]:
    payload = cast("JsonValue", json.loads(value)) if isinstance(value, str) else value
    assert isinstance(payload, dict)
    return payload


def _json_list(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _db_dump(db_path: Path) -> str:
    with sqlite3.connect(db_path) as conn:
        return "\n".join(conn.iterdump())


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
