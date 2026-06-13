from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.state import STATE_DIR, JsonValue

ACADEMY_SCHEMA_VERSION = "academy-v3"
ACADEMY_STATE_DIR = "academy"
ACADEMY_STORE_FILE = "academy-store.json"


def test_academy_db_inspect_reports_v3_counts_without_path_leaks(tmp_path: Path) -> None:
    # Given: an initialized private academy DB profile.
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")

    # When: the V3 inspect command is run.
    inspect_result = _run_cli("academy-db", "inspect", "--profile-root", str(tmp_path), "--json")

    # Then: the output describes the empty V3 store without leaking the private path.
    assert init_result.returncode == 0, init_result.stderr
    assert inspect_result.returncode == 0, inspect_result.stderr
    payload = _json_payload(inspect_result)
    assert payload["status"] == "PASS"
    assert payload["schema_version"] == ACADEMY_SCHEMA_VERSION
    assert payload["store"] == "<profile-root>/.chat-lms-state/academy/academy-store.json"
    assert payload["counts"] == {"classes": 0, "learners": 0, "lessons": 0, "records": 0}
    _assert_no_path_leak(inspect_result, tmp_path)


def test_academy_db_schema_show_reports_entities_and_named_query_params(
    tmp_path: Path,
) -> None:
    # Given: a private profile root for schema inspection.

    # When: the V3 schema command is run.
    result = _run_cli(
        "academy-db",
        "schema",
        "show",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the schema includes entities and parameter schemas for named queries.
    assert result.returncode == 0, result.stderr
    payload = _json_payload(result)
    assert payload["status"] == "PASS"
    assert payload["schema_version"] == ACADEMY_SCHEMA_VERSION
    assert sorted(payload["entities"]) == ["classes", "learners", "lessons"]
    named_queries = payload["named_queries"]
    assert isinstance(named_queries, dict)
    learner_count = named_queries["learner-count"]
    assert isinstance(learner_count, dict)
    assert learner_count["params"] == {
        "class_id": {"required": False, "type": "string"},
    }
    _assert_no_path_leak(result, tmp_path)


def test_academy_db_query_run_uses_params_file_without_path_leaks(tmp_path: Path) -> None:
    # Given: a V3 academy store with learners across two public-demo classes.
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    assert init_result.returncode == 0, init_result.stderr
    _write_store(
        tmp_path,
        {
            "schema_version": ACADEMY_SCHEMA_VERSION,
            "classes": [
                {"class_id": "public-class-a", "name": "Public Class A"},
                {"class_id": "public-class-b", "name": "Public Class B"},
            ],
            "learners": [
                {"class_id": "public-class-a", "learner_id": "public-learner-1"},
                {"class_id": "public-class-b", "learner_id": "public-learner-2"},
            ],
            "lessons": [],
        },
    )
    params_path = tmp_path / "learner-count-params.json"
    params_path.write_text(
        json.dumps({"class_id": "public-class-a"}, ensure_ascii=False),
        encoding="utf-8",
    )

    # When: the learner-count named query is run with a params JSON file.
    result = _run_cli(
        "academy-db",
        "query",
        "run",
        "--name",
        "learner-count",
        "--params",
        str(params_path),
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the query applies the params and keeps temp file paths out of stdout.
    assert result.returncode == 0, result.stderr
    payload = _json_payload(result)
    assert payload["status"] == "PASS"
    assert payload["query"] == "learner-count"
    assert payload["params"] == {"class_id": "public-class-a"}
    assert payload["result"] == {"count": 1}
    _assert_no_path_leak(result, tmp_path)
    _assert_no_path_leak(result, params_path)


def test_academy_db_query_run_rejects_invalid_params_schema(tmp_path: Path) -> None:
    # Given: a V3 query params file with an invalid type and unknown key.
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    assert init_result.returncode == 0, init_result.stderr
    params_path = tmp_path / "bad-params.json"
    params_path.write_text(
        json.dumps({"class_id": 123, "unsafe": "ignored"}, ensure_ascii=False),
        encoding="utf-8",
    )

    # When: the params are passed to a named query.
    result = _run_cli(
        "academy-db",
        "query",
        "run",
        "--name",
        "learner-count",
        "--params",
        str(params_path),
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the query refuses unsafe/ill-typed params before running.
    assert result.returncode == 2
    payload = _json_payload(result)
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "INVALID_QUERY_PARAMS"
    _assert_no_path_leak(result, tmp_path)
    _assert_no_path_leak(result, params_path)


def test_academy_db_import_plan_rejects_unsafe_public_repo_source(
    tmp_path: Path,
) -> None:
    # Given: a non-fixture source path from the public repository.
    unsafe_source = _repo_root() / "README.md"

    # When: an academy DB import plan is requested for that source.
    result = _run_cli(
        "academy-db",
        "import",
        "plan",
        "--from",
        str(unsafe_source),
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the source is rejected as unsafe and no local paths are printed.
    assert result.returncode != 0
    payload = _json_payload(result)
    assert payload["status"] == "UNSAFE"
    assert payload["error_code"] == "ACADEMY_IMPORT_SOURCE_UNSAFE"
    _assert_no_path_leak(result, unsafe_source)
    _assert_no_path_leak(result, tmp_path)


def test_academy_db_import_plan_accepts_public_safe_fixture_needing_approval(
    tmp_path: Path,
) -> None:
    # Given: a public-safe import fixture committed under tests/fixtures.
    safe_source = _repo_root() / "tests" / "fixtures" / "academy_db" / "public_safe_import.json"

    # When: an import plan is requested for the public-safe fixture.
    result = _run_cli(
        "academy-db",
        "import",
        "plan",
        "--from",
        str(safe_source),
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: a dry plan is produced and explicit approval is still required.
    assert result.returncode == 0, result.stderr
    payload = _json_payload(result)
    assert payload["status"] == "NEEDS_APPROVAL"
    assert payload["plan_id"]
    assert payload["writes"] == []
    _assert_no_path_leak(result, safe_source)
    _assert_no_path_leak(result, tmp_path)


def test_academy_db_doctor_reports_v3_checks(tmp_path: Path) -> None:
    # Given: a private profile root for academy DB diagnostics.

    # When: the academy DB doctor command is run.
    result = _run_cli("academy-db", "doctor", "--profile-root", str(tmp_path), "--json")

    # Then: the diagnostic result includes V3 academy DB checks.
    assert result.returncode == 0, result.stderr
    payload = _json_payload(result)
    assert payload["status"] == "PASS"
    assert payload["schema_version"] == ACADEMY_SCHEMA_VERSION
    checks = payload["checks"]
    assert isinstance(checks, list)
    check_ids = [check["id"] for check in checks if isinstance(check, dict)]
    assert "academy-db-schema-v3" in check_ids
    assert "academy-db-import-safety-v3" in check_ids
    _assert_no_path_leak(result, tmp_path)


def _write_store(profile_root: Path, payload: dict[str, JsonValue]) -> None:
    store_path = profile_root / STATE_DIR / ACADEMY_STATE_DIR / ACADEMY_STORE_FILE
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _json_payload(result: subprocess.CompletedProcess[str]) -> dict[str, JsonValue]:
    payload: JsonValue = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def _assert_no_path_leak(result: subprocess.CompletedProcess[str], path: Path) -> None:
    raw_path = str(path)
    json_escaped_path = raw_path.replace("\\", "\\\\")
    assert raw_path not in result.stdout
    assert json_escaped_path not in result.stdout


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
