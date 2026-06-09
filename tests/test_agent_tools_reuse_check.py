from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_reuse_check_finds_existing_side_panel_tool_for_panel_intent() -> None:
    # Given: an agent intent that can be served by an existing side-panel tool.
    # When: the agent runs the reuse-before-build gate.
    result = _run_cli(
        "agent-tools",
        "reuse-check",
        "--intent",
        "build side panel for an academy DB report",
        "--json",
    )

    # Then: the existing side-panel surface is returned before any scaffold.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["decision"] == "reuse_existing"
    assert "side-panel" in {match["id"] for match in payload["matches"]}
    assert payload["checked"]["existing_chat_lms_commands"] is True
    assert payload["checked"]["existing_skills"] is True
    assert payload["checked"]["oss_candidates"] is True


def test_validate_rejects_tool_without_reuse_review(tmp_path: Path) -> None:
    # Given: a proposal that has the old required fields but no reuse review.
    proposal = {
        "id": "new-report-tool",
        "summary": "Create a new report tool.",
        "command_contract": {"command": "python -m chat_lms_agent report build"},
        "memory_obligation": "Record tool:new-report-tool before use.",
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    # When: validating the proposal.
    result = _run_cli("agent-tools", "validate", "--from", str(proposal_path), "--json")

    # Then: custom tool creation is blocked until reuse was checked.
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert "MISSING_REUSE_REVIEW" in payload["errors"]


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
