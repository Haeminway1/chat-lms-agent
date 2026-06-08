from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_doctor_json_contract_passes_on_fresh_repo() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_module(repo_root, "doctor", "--repair", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] in {"PASS", "REPAIRED"}
    assert payload["exit_code"] == 0
    assert isinstance(payload["checks"], list)
    assert {check["id"] for check in payload["checks"]} >= {"package", "plugin", "skills"}


def test_doctor_redacts_credentials() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["GOOGLE_" + "CLIENT_SECRET"] = "secret-value-that-must-not-leak"

    result = subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", "doctor", "--repair", "--json"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "secret-value-that-must-not-leak" not in result.stdout


def _run_module(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
