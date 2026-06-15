from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


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
