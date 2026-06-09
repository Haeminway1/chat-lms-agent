from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_registry_path_change_requires_tool_memory_draft() -> None:
    result = _run_cli(
        "memory",
        "verify",
        "--changed-files",
        "src/chat_lms_agent/agent_tools.py",
        "--json",
    )

    assert result.returncode == 5
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "MEMORY_UPDATE_REQUIRED"
    assert payload["missing_memory"] == ["tool:agent-tools"]
    assert payload["drafts"][0]["key"] == "tool:agent-tools"


def test_db_schema_change_requires_schema_and_decision_memory() -> None:
    result = _run_cli(
        "memory",
        "verify",
        "--changed-files",
        "src/chat_lms_agent/academy_db/schema.py",
        "--json",
    )

    assert result.returncode == 5
    payload = json.loads(result.stdout)
    assert payload["missing_memory"] == ["decision:academy-db-schema", "schema:academy-db"]


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
