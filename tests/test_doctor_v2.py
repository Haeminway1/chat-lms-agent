from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_doctor_reports_v2_harness_checks() -> None:
    result = _run_cli("doctor", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    checks = {check["id"]: check for check in payload["checks"]}
    assert {"hooks_lifecycle", "memory_obligations", "academy_db", "runtime_boundary"} <= set(
        checks,
    )
    assert checks["hooks_lifecycle"]["status"] == "PASS"


def test_doctor_reports_unresolved_memory_obligation(tmp_path: Path) -> None:
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    doctor_result = _run_cli("doctor", "--profile-root", str(tmp_path), "--json")

    assert init_result.returncode == 0, init_result.stderr
    assert doctor_result.returncode == 5
    payload = json.loads(doctor_result.stdout)
    checks = {check["id"]: check for check in payload["checks"]}
    assert checks["memory_obligations"]["status"] == "NEEDS_APPROVAL"


def test_doctor_reports_public_repo_runtime_boundary() -> None:
    result = _run_cli("doctor", "--profile-root", str(_repo_root()), "--json")

    assert result.returncode == 4
    payload = json.loads(result.stdout)
    checks = {check["id"]: check for check in payload["checks"]}
    assert checks["runtime_boundary"]["status"] == "UNSAFE"


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
