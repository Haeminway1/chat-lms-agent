from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_harness_v2_end_to_end_temp_profile(tmp_path: Path) -> None:
    proposal_path = tmp_path / "tool.json"
    draft_path = tmp_path / "memory.json"
    proposal_path.write_text(json.dumps(_valid_tool_proposal()), encoding="utf-8")

    commands = [
        ("academy-db", "init", "--profile-root", str(tmp_path), "--json"),
        (
            "academy-db",
            "query",
            "run",
            "--name",
            "learner-count",
            "--profile-root",
            str(tmp_path),
            "--json",
        ),
        (
            "academy-db",
            "report",
            "build",
            "--report",
            "class-overview",
            "--profile-root",
            str(tmp_path),
            "--json",
        ),
        ("academy-db", "backup", "create", "--profile-root", str(tmp_path), "--json"),
        (
            "academy-db",
            "migrate",
            "apply",
            "--to",
            "next",
            "--profile-root",
            str(tmp_path),
            "--json",
        ),
        (
            "agent-tools",
            "scaffold",
            "--from",
            str(proposal_path),
            "--profile-root",
            str(tmp_path),
            "--json",
        ),
        (
            "agent-tools",
            "promote",
            "--id",
            "attendance-risk",
            "--profile-root",
            str(tmp_path),
            "--json",
        ),
        (
            "memory",
            "draft",
            "--for",
            "academy-db-init",
            "--out",
            str(draft_path),
            "--profile-root",
            str(tmp_path),
            "--json",
        ),
        (
            "memory",
            "apply-draft",
            "--from",
            str(draft_path),
            "--profile-root",
            str(tmp_path),
            "--json",
        ),
        ("context", "hydrate", "--for-codex", "--profile-root", str(tmp_path), "--json"),
        ("session", "closeout", "--verify-memory", "--profile-root", str(tmp_path), "--json"),
        ("doctor", "--profile-root", str(tmp_path), "--json"),
    ]

    results = [_run_cli(*command) for command in commands]

    assert [result.returncode for result in results] == [0] * len(commands)
    context_payload = json.loads(results[-3].stdout)
    closeout_payload = json.loads(results[-2].stdout)
    doctor_payload = json.loads(results[-1].stdout)
    assert context_payload["academy_db"]["initialized"] is True
    assert closeout_payload["status"] == "PASS"
    assert doctor_payload["status"] == "PASS"
    assert str(tmp_path) not in results[-3].stdout


def _valid_tool_proposal() -> dict[str, object]:
    return {
        "id": "attendance-risk",
        "label": "Attendance Risk",
        "summary": "Find synthetic attendance risk from private profile data.",
        "command_contract": {
            "commands": [
                "python -m chat_lms_agent academy-db query run --name learner-count --json",
            ],
        },
        "memory_obligation": {
            "key": "tool:attendance-risk",
            "scope": "tool-registry",
            "text": "Use attendance-risk only through the academy-db CLI.",
        },
        "safety_boundary": {"public_safe": True},
        "test_contract": {"command": "uv run pytest tests/test_harness_v2_integration.py -q"},
        "reuse_review": {
            "checked_existing": ["academy-db query run", "agent-tools list"],
            "custom_build_justification": "Attendance risk is a reusable synthetic workflow.",
        },
    }


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
