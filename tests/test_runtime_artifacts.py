from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_public_repo_rejects_academy_db_root() -> None:
    result = _run_cli("academy-db", "init", "--profile-root", str(_repo_root()), "--json")

    assert result.returncode == 4
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "PUBLIC_REPO_STATE_REJECTED"


def test_public_repo_child_rejects_academy_db_root() -> None:
    result = _run_cli(
        "academy-db",
        "init",
        "--profile-root",
        str(_repo_root() / ".tmp-academy-profile"),
        "--json",
    )

    assert result.returncode == 4
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "PUBLIC_REPO_STATE_REJECTED"


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
