from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SESSION_ID = "019ed3d3-b07d-7aa0-9722-40b75b22ba6f"


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
        input="",
    )


def _seed_rollout(codex_home: Path) -> None:
    day = codex_home / "sessions" / "2026" / "06" / "17"
    day.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "timestamp": "2026-06-17T04:25:31Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "EBSS record please"},
        },
        {
            "timestamp": "2026-06-17T04:25:33Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell",
                "arguments": "{}",
                "call_id": "call_1",
            },
        },
    ]
    blob = "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    _ = (day / f"rollout-2026-06-17T13-25-26-{SESSION_ID}.jsonl").write_text(
        blob,
        encoding="utf-8",
    )


def test_cli_ingest_list_show_roundtrip(tmp_path: Path) -> None:
    profile_root = tmp_path / "profile"
    codex_home = tmp_path / "codex-home"
    _seed_rollout(codex_home)

    ingest = _run_cli(
        "session-log",
        "ingest",
        "--transcript-home",
        str(codex_home),
        "--profile-root",
        str(profile_root),
        "--json",
    )
    listing = _run_cli("session-log", "list", "--profile-root", str(profile_root), "--json")
    show = _run_cli(
        "session-log",
        "show",
        "--session-id",
        SESSION_ID,
        "--profile-root",
        str(profile_root),
        "--json",
    )

    assert ingest.returncode == 0, ingest.stdout + ingest.stderr
    assert json.loads(ingest.stdout)["records_appended"] == 2
    assert listing.returncode == 0, listing.stdout
    assert json.loads(listing.stdout)["session_count"] == 1
    assert show.returncode == 0, show.stdout
    show_payload = json.loads(show.stdout)
    assert show_payload["record_count"] == 2
    assert str(profile_root) not in show.stdout


def test_cli_status_enable_disable(tmp_path: Path) -> None:
    profile_root = tmp_path / "profile"

    status = _run_cli("session-log", "status", "--profile-root", str(profile_root), "--json")
    disable = _run_cli("session-log", "disable", "--profile-root", str(profile_root), "--json")
    status_after = _run_cli("session-log", "status", "--profile-root", str(profile_root), "--json")
    enable = _run_cli("session-log", "enable", "--profile-root", str(profile_root), "--json")

    assert json.loads(status.stdout)["enabled"] is True
    assert json.loads(disable.stdout)["enabled"] is False
    assert json.loads(status_after.stdout)["enabled"] is False
    assert json.loads(enable.stdout)["enabled"] is True


def test_cli_show_missing_session_errors(tmp_path: Path) -> None:
    profile_root = tmp_path / "profile"
    result = _run_cli(
        "session-log",
        "show",
        "--session-id",
        "no-such-session",
        "--profile-root",
        str(profile_root),
        "--json",
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["error_code"] == "SESSION_NOT_FOUND"


def test_cli_rejects_public_repo_profile_root() -> None:
    result = _run_cli(
        "session-log",
        "ingest",
        "--profile-root",
        str(_repo_root()),
        "--json",
    )
    assert result.returncode == 4
    assert json.loads(result.stdout)["error_code"] == "PUBLIC_REPO_STATE_REJECTED"
