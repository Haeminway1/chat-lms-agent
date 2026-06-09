from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_report_build_writes_only_private_report_root(tmp_path: Path) -> None:
    init_result = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    report_result = _run_cli(
        "academy-db",
        "report",
        "build",
        "--profile-root",
        str(tmp_path),
        "--report",
        "class-overview",
        "--json",
    )

    assert init_result.returncode == 0, init_result.stderr
    assert report_result.returncode == 0, report_result.stderr
    payload = json.loads(report_result.stdout)
    assert payload["report"] == "class-overview"
    assert payload["path"] == "<profile-root>/.chat-lms-state/academy/reports/class-overview.json"
    assert str(tmp_path) not in report_result.stdout


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
