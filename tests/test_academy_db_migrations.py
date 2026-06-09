from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_migration_apply_requires_backup(tmp_path: Path) -> None:
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    plan_result = _run_cli(
        "academy-db",
        "migrate",
        "plan",
        "--profile-root",
        str(tmp_path),
        "--to",
        "next",
        "--json",
    )
    apply_result = _run_cli(
        "academy-db",
        "migrate",
        "apply",
        "--profile-root",
        str(tmp_path),
        "--to",
        "next",
        "--json",
    )

    assert init_result.returncode == 0, init_result.stderr
    assert plan_result.returncode == 0, plan_result.stderr
    assert apply_result.returncode == 2
    assert json.loads(apply_result.stdout)["error_code"] == "BACKUP_REQUIRED"


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
