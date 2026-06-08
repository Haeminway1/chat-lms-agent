from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_malformed_answers_json_returns_validation_error_without_traceback_or_secret() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    answers_path = repo_root / "tests" / "fixtures" / "onboarding_malformed.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["API_" + "TOKEN"] = "token-that-must-not-leak"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chat_lms_agent",
            "onboarding",
            "start",
            "--mode",
            "guided",
            "--answers",
            str(answers_path),
            "--dry-run",
            "--json",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "VALIDATION_ERROR"
    assert "Traceback" not in result.stderr
    assert "token-that-must-not-leak" not in result.stdout
    assert "token-that-must-not-leak" not in result.stderr


def test_bom_prefixed_answers_json_is_accepted(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    answers_path = tmp_path / "onboarding_bom.json"
    answers_path.write_bytes(b'\xef\xbb\xbf{"mode": "guided"}\n')
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chat_lms_agent",
            "onboarding",
            "start",
            "--mode",
            "guided",
            "--answers",
            str(answers_path),
            "--dry-run",
            "--json",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "READY"
