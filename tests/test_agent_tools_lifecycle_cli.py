from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_agent_tools_scaffold_promote_explain_and_deprecate(tmp_path: Path) -> None:
    proposal_path = tmp_path / "valid-tool.json"
    proposal_path.write_text(json.dumps(_valid_tool_proposal()), encoding="utf-8")

    scaffold = _run_cli(
        "agent-tools",
        "scaffold",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(proposal_path),
        "--json",
    )
    promote = _run_cli(
        "agent-tools",
        "promote",
        "--profile-root",
        str(tmp_path),
        "--id",
        "attendance-risk",
        "--json",
    )
    explain = _run_cli(
        "agent-tools",
        "explain",
        "--profile-root",
        str(tmp_path),
        "--id",
        "attendance-risk",
        "--json",
    )
    deprecate = _run_cli(
        "agent-tools",
        "deprecate",
        "--profile-root",
        str(tmp_path),
        "--id",
        "attendance-risk",
        "--json",
    )

    assert scaffold.returncode == 0, scaffold.stderr
    assert promote.returncode == 0, promote.stderr
    assert explain.returncode == 0, explain.stderr
    assert deprecate.returncode == 0, deprecate.stderr
    assert json.loads(scaffold.stdout)["lifecycle_state"] == "draft"
    assert json.loads(promote.stdout)["lifecycle_state"] == "active"
    explain_payload = json.loads(explain.stdout)
    assert explain_payload["tool"]["id"] == "attendance-risk"
    assert explain_payload["tool"]["memory_obligation"]["key"] == "tool:attendance-risk"
    assert json.loads(deprecate.stdout)["lifecycle_state"] == "deprecated"


def test_agent_tools_scaffold_requires_safety_and_test_contracts(tmp_path: Path) -> None:
    proposal_path = tmp_path / "unsafe-tool.json"
    proposal_path.write_text(
        json.dumps({"id": "unsafe-tool", "summary": "Missing contracts."}),
        encoding="utf-8",
    )

    result = _run_cli(
        "agent-tools",
        "scaffold",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(proposal_path),
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "INVALID_TOOL_PROPOSAL"
    assert {"MISSING_SAFETY_BOUNDARY", "MISSING_TEST_CONTRACT"} <= set(payload["errors"])


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
        "safety_boundary": {
            "public_safe": True,
            "runtime_data": "private-profile-only",
        },
        "test_contract": {
            "command": "uv run pytest tests/test_agent_tools_lifecycle_cli.py -q",
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
