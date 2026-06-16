from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from chat_lms_agent.write_action_handlers import handle_write_action

if TYPE_CHECKING:
    import pytest
    from _pytest.capture import CaptureFixture

    from chat_lms_agent.state import JsonValue, ProfileState
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
    # Given: a template, payload, and synthetic database under the profile data root.
    fixture = _db_fixture(tmp_path)
    _write_template(tmp_path, _template_payload("daily"))
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


def test_write_action_apply_maps_engine_unsafe_and_error(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: payloads that force engine ERROR and UNSAFE outcomes.
    error_root = tmp_path / "error-profile"
    unsafe_root = tmp_path / "unsafe-profile"
    _write_template(error_root, _template_payload("daily"))
    _write_template(unsafe_root, _template_payload("daily"))
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
    assert valid_payload["template_count"] == 1
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
            CREATE TABLE students(id INTEGER PRIMARY KEY, canonical_name TEXT UNIQUE);
            CREATE TABLE enrollments(
              id INTEGER PRIMARY KEY,
              student_id INTEGER,
              class_id INTEGER,
              status TEXT
            );
            INSERT INTO classes(id, code, canonical_name)
            VALUES (1, 'alpha', 'Fictional Alpha Class');
            INSERT INTO students(id, canonical_name)
            VALUES
              (1, 'Fictional Ada'),
              (2, 'Fictional Ben'),
              (3, 'Fictional Cora');
            INSERT INTO enrollments(student_id, class_id, status)
            VALUES
              (1, 1, 'active'),
              (2, 1, 'active'),
              (3, 1, 'inactive');
            """,
        )


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
