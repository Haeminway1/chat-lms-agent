from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_agent_tools_route_record_counts_known_route(tmp_path: Path) -> None:
    # Given: a fresh profile and the repo-shipped lesson route pack.
    profile_root = tmp_path / "profile"

    # When: the route catalog use is recorded.
    result = _run_cli(
        "agent-tools",
        "route",
        "record",
        "--route-id",
        "lesson_assistant_panel",
        "--profile-root",
        str(profile_root),
        "--json",
    )

    # Then: zero-content route telemetry is incremented.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["route_id"] == "lesson_assistant_panel"
    telemetry = json.loads(
        (profile_root / ".chat-lms-state" / "usage-telemetry.json").read_text(
            encoding="utf-8",
        ),
    )
    assert telemetry["route-catalog:lesson_assistant_panel"]["count"] == 1


def test_agent_tools_route_record_rejects_unknown_route(tmp_path: Path) -> None:
    # Given: a fresh profile.
    profile_root = tmp_path / "profile"

    # When: an unknown route id is recorded.
    result = _run_cli(
        "agent-tools",
        "route",
        "record",
        "--route-id",
        "missing_route",
        "--profile-root",
        str(profile_root),
        "--json",
    )

    # Then: validation fails before telemetry is written.
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "UNKNOWN_ROUTE_ID"
    assert not (profile_root / ".chat-lms-state" / "usage-telemetry.json").exists()


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=repo_root,
        env=env,
        input="",
        capture_output=True,
        check=False,
        text=True,
    )
