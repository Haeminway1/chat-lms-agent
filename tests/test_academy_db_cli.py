from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.state import STATE_DIR, JsonValue


def test_academy_db_spec_init_and_query_list(tmp_path: Path) -> None:
    spec_result = _run_cli("academy-db", "spec", "--json")
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    query_result = _run_cli(
        "academy-db",
        "query",
        "list",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    assert spec_result.returncode == 0
    assert init_result.returncode == 0
    assert query_result.returncode == 0
    spec_payload = json.loads(spec_result.stdout)
    init_payload = json.loads(init_result.stdout)
    query_payload = json.loads(query_result.stdout)
    assert spec_payload["public_safe"] is True
    assert init_payload["schema_version"] == spec_payload["schema_version"]
    assert "learner-count" in query_payload["queries"]
    assert str(tmp_path) not in init_result.stdout


def test_academy_db_record_types_list_shows_repo_and_profile_sources(tmp_path: Path) -> None:
    # Given: a profile record-type file overriding the repo attendance default.
    _write_record_type(
        tmp_path,
        "attendance.json",
        {
            "schema_version": "record-type-v1",
            "id": "attendance",
            "label": "출결 커스텀",
            "target": "learner",
            "fields": [
                {"name": "date", "type": "date", "required": True},
                {
                    "name": "status",
                    "type": "enum",
                    "required": True,
                    "options": ["출석", "결석"],
                },
            ],
        },
    )

    # When: the academy-db record-type registry is listed through the CLI.
    result = _run_cli(
        "academy-db",
        "record-types",
        "list",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: repo defaults and profile overrides are visible without leaking paths.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    records = payload["record_types"]
    assert isinstance(records, list)
    by_id = {
        item["id"]: item
        for item in records
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    assert by_id["attendance"]["source"] == "profile"
    assert by_id["attendance"]["label"] == "출결 커스텀"
    assert by_id["attendance"]["target"] == "learner"
    assert by_id["attendance"]["fields"] == [
        {"name": "date", "type": "date", "required": True},
        {
            "name": "status",
            "type": "enum",
            "required": True,
            "options": ["출석", "결석"],
        },
    ]
    assert by_id["journal"]["source"] == "repo"
    assert by_id["journal"]["fields"][1]["options"] == ["완료", "부분완료", "미완료"]
    assert payload["warnings"] == []
    assert str(tmp_path) not in result.stdout


def _write_record_type(root: Path, name: str, payload: dict[str, JsonValue]) -> None:
    record_types_dir = root / STATE_DIR / "record-types"
    record_types_dir.mkdir(parents=True, exist_ok=True)
    (record_types_dir / name).write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


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
