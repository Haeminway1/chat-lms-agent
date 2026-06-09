from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_harness_event_normalize_preserves_codex_hook_source_event(tmp_path: Path) -> None:
    payload_path = tmp_path / "codex-hook.json"
    payload_path.write_text(
        json.dumps(
            {
                "host": "codex_desktop",
                "hook_event_name": "UserPromptSubmit",
                "session_id": "session-red-001",
                "transcript_path": str(tmp_path / "transcript.jsonl"),
                "prompt": "Summarize today's attendance.",
            },
        ),
        encoding="utf-8",
    )

    result = _run_cli("harness", "event", "normalize", "--from", str(payload_path), "--json")

    assert result.returncode == 0, result.stderr
    normalized = json.loads(result.stdout)
    assert normalized["status"] == "PASS"
    assert normalized["schema_version"] == "harness-event-v1"
    assert normalized["host"] == "codex_desktop"
    assert normalized["event_type"] == "user_prompt_submit"
    assert normalized["source_event_name"] == "UserPromptSubmit"
    assert normalized["session_id"] == "session-red-001"


def test_harness_event_normalize_accepts_future_standalone_desktop_host(
    tmp_path: Path,
) -> None:
    payload_path = tmp_path / "standalone-event.json"
    payload_path.write_text(
        json.dumps(
            {
                "host": "standalone_desktop",
                "event_type": "session_start",
                "event_name": "session_start",
                "session_id": "standalone-red-001",
            },
        ),
        encoding="utf-8",
    )

    result = _run_cli("harness", "event", "normalize", "--from", str(payload_path), "--json")

    assert result.returncode == 0, result.stderr
    normalized = json.loads(result.stdout)
    assert normalized["status"] == "PASS"
    assert normalized["schema_version"] == "harness-event-v1"
    assert normalized["host"] == "standalone_desktop"
    assert normalized["event_type"] == "session_start"
    assert normalized["source_event_name"] == "session_start"
    assert normalized["session_id"] == "standalone-red-001"


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
