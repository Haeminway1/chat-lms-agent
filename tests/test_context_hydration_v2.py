from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_hydrate_includes_hook_memory_tool_and_academy_inventory(tmp_path: Path) -> None:
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    hydrate_result = _run_cli(
        "context",
        "hydrate",
        "--profile-root",
        str(tmp_path),
        "--for-codex",
        "--json",
    )

    assert init_result.returncode == 0, init_result.stderr
    assert hydrate_result.returncode == 0, hydrate_result.stderr
    payload = json.loads(hydrate_result.stdout)
    assert {"hook_lifecycle", "memory_obligations", "tool_lifecycle", "academy_db"} <= set(
        payload,
    )
    assert payload["academy_db"]["schema_version"] == "academy-v1"
    assert payload["hook_lifecycle"]["registered_events"] == [
        "PostCompact",
        "PostToolUse",
        "SessionStart",
        "Stop",
        "UserPromptSubmit",
    ]


def test_hydrate_does_not_leak_private_runtime_paths(tmp_path: Path) -> None:
    result = _run_cli(
        "context",
        "hydrate",
        "--profile-root",
        str(tmp_path),
        "--for-codex",
        "--json",
    )

    assert result.returncode == 0, result.stderr
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
