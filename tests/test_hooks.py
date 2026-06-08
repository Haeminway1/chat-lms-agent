from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_hooks_config_registers_session_start_and_stop() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    hooks_path = repo_root / "hooks" / "hooks.json"

    hooks = json.loads(hooks_path.read_text(encoding="utf-8"))

    assert "SessionStart" in hooks
    assert "Stop" in hooks


def test_context_hydrate_outputs_redacted_codex_context() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["CLASSCARD_PASSWORD"] = "should-not-leak"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "chat_lms_agent",
            "context",
            "hydrate",
            "--for-codex",
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
    assert payload["status"] == "PASS"
    assert payload["runtime"] == "Codex Desktop"
    assert "should-not-leak" not in result.stdout
