from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_lesson_open_plan_blocks_when_runtime_assets_are_missing(tmp_path: Path) -> None:
    # Given: an assetless private profile.
    profile_root = tmp_path / "profile"

    # When: the lesson assistant panel is requested.
    result = _run_cli(
        "side-panel",
        "lesson",
        "open-plan",
        "--student",
        "Synthetic Learner",
        "--date",
        "2026-06-12",
        "--profile-root",
        str(profile_root),
        "--json",
    )

    # Then: Wave 2 exposes only the blocked install-assets path.
    assert result.returncode in {4, 5}
    payload = json.loads(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["kind"] == "lesson_assistant_panel"
    assert payload["error_code"] == "LESSON_RUNTIME_MISSING"
    assert "side-panel lesson install-assets" in payload["next_action"]
    assert payload["runtime_assets"]["server"].endswith("lesson_panel_server.py")
    assert payload["runtime_assets"]["view"].endswith("lesson_panel_view.html")
    assert str(profile_root) not in result.stdout


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
