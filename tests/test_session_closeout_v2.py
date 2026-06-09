from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_closeout_blocks_academy_db_schema_change_without_decision(tmp_path: Path) -> None:
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    closeout_result = _run_cli(
        "session",
        "closeout",
        "--profile-root",
        str(tmp_path),
        "--verify-memory",
        "--json",
    )

    assert init_result.returncode == 0, init_result.stderr
    assert closeout_result.returncode == 5
    payload = json.loads(closeout_result.stdout)
    assert payload["missing_memory"] == ["decision:academy-db-schema", "schema:academy-db"]


def test_closeout_passes_after_academy_db_memory_draft_is_applied(tmp_path: Path) -> None:
    draft_path = tmp_path / "memory.json"
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    draft_result = _run_cli(
        "memory",
        "draft",
        "--profile-root",
        str(tmp_path),
        "--for",
        "academy-db-init",
        "--out",
        str(draft_path),
        "--json",
    )
    apply_result = _run_cli(
        "memory",
        "apply-draft",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(draft_path),
        "--json",
    )
    closeout_result = _run_cli(
        "session",
        "closeout",
        "--profile-root",
        str(tmp_path),
        "--verify-memory",
        "--json",
    )

    assert init_result.returncode == 0, init_result.stderr
    assert draft_result.returncode == 0, draft_result.stderr
    assert apply_result.returncode == 0, apply_result.stderr
    assert closeout_result.returncode == 0, closeout_result.stdout
    assert json.loads(closeout_result.stdout)["status"] == "PASS"


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
