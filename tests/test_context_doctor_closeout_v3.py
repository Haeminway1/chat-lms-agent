from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_context_hydrate_includes_v3_operating_inventory(tmp_path: Path) -> None:
    # Given: a private profile with an initialized academy DB.
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")

    # When: hydrating context for a new Codex session.
    hydrate_result = _run_cli(
        "context",
        "hydrate",
        "--profile-root",
        str(tmp_path),
        "--for-codex",
        "--json",
    )

    # Then: V3 top-level operating surfaces are available and path-redacted.
    assert init_result.returncode == 0, init_result.stderr
    assert hydrate_result.returncode == 0, hydrate_result.stderr
    payload = json.loads(hydrate_result.stdout)
    assert {
        "harness",
        "trace",
        "audit",
        "approvals",
        "academy_db",
    } <= set(payload)
    assert payload["harness"]["schema_version"] == "harness-context-v3"
    assert payload["trace"]["schema_version"] == "trace-v1"
    assert payload["audit"]["schema_version"] == "audit-v1"
    assert payload["approvals"]["schema_version"] == "approval-v1"
    assert payload["academy_db"]["schema_version"] == "academy-v1"
    assert "entities" in payload["academy_db"]["schema"]
    assert "learner-count" in payload["academy_db"]["query_inventory"]
    assert str(tmp_path) not in hydrate_result.stdout


def test_doctor_reports_v3_trace_audit_approval_and_academy_checks(
    tmp_path: Path,
) -> None:
    # Given: a private profile available for V3 smoke checks.
    profile_root = tmp_path / "profile"
    profile_root.mkdir()

    # When: running doctor for the profile.
    doctor_result = _run_cli("doctor", "--profile-root", str(profile_root), "--json")

    # Then: doctor reports the V3 operating ledgers and DB pack.
    assert doctor_result.returncode == 0, doctor_result.stdout
    payload = json.loads(doctor_result.stdout)
    checks = {check["id"]: check for check in payload["checks"]}
    assert {
        "trace_journal",
        "audit_ledger",
        "approval_ledger",
        "academy_db_v3",
    } <= set(checks)
    assert checks["trace_journal"]["status"] == "PASS"
    assert checks["audit_ledger"]["status"] == "PASS"
    assert checks["approval_ledger"]["status"] == "PASS"
    assert checks["academy_db_v3"]["status"] == "PASS"
    assert str(profile_root) not in doctor_result.stdout


def test_session_closeout_blocks_pending_approval_and_unapplied_import_plan(
    tmp_path: Path,
) -> None:
    # Given: risky V3 work remains unresolved in private profile state.
    state_dir = tmp_path / ".chat-lms-state"
    approvals_dir = state_dir / "approvals"
    imports_dir = state_dir / "academy" / "imports"
    approvals_dir.mkdir(parents=True)
    imports_dir.mkdir(parents=True)
    _write_json(
        approvals_dir / "approvals.json",
        {
            "approvals": [
                {
                    "schema_version": "approval-v1",
                    "approval_id": "approval_import_001",
                    "plan_id": "import_plan_001",
                    "operation": "academy-db.import.apply",
                    "status": "planned",
                    "requested_by": "codex_desktop_agent",
                    "approved_by": None,
                },
            ],
        },
    )
    _write_json(
        imports_dir / "import-plans.json",
        {
            "plans": [
                {
                    "schema_version": "academy-import-plan-v1",
                    "plan_id": "import_plan_001",
                    "status": "NEEDS_APPROVAL",
                    "profile_root": "<profile-root>",
                },
            ],
        },
    )

    # When: closing out the session.
    result = _run_cli("session", "closeout", "--profile-root", str(tmp_path), "--json")

    # Then: closeout blocks until the risky work is resolved.
    assert result.returncode == 5, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["pending_approvals"] == ["approval_import_001"]
    assert payload["unapplied_import_plans"] == ["import_plan_001"]
    assert str(tmp_path) not in result.stdout


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


def _write_json(path: Path, payload: dict[str, list[dict[str, str | None]]]) -> None:
    _ = path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
