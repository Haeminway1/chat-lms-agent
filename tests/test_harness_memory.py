from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_hook_stop_requires_memory_update_for_agent_tool_registry_change() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    result = _run_cli(
        repo_root,
        "hook",
        "stop",
        "--verify-memory",
        "--changed-files",
        "src/chat_lms_agent/agent_tools.py",
        "--json",
    )

    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["error_code"] == "MEMORY_UPDATE_REQUIRED"
    assert "src/chat_lms_agent/agent_tools.py" in payload["changed_files"]


def test_hook_stop_allows_registry_change_with_memory_update_flag() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    result = _run_cli(
        repo_root,
        "hook",
        "stop",
        "--verify-memory",
        "--changed-files",
        "src/chat_lms_agent/agent_tools.py",
        "--memory-updated",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"


def _run_cli(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
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
