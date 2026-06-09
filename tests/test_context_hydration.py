from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_hydrate_includes_side_panel_contract_shape() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    result = subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", "context", "hydrate", "--for-codex", "--json"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    side_panel = payload["side_panel"]
    assert side_panel["official_name"] == "보조 패널(side panel)"
    assert side_panel["user_owned_html_css"] is True
    assert "class_overview" in side_panel["views"]
