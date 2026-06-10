from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_agent_tools_scaffold_promote_explain_and_deprecate(tmp_path: Path) -> None:
    proposal_path = tmp_path / "valid-tool.json"
    proposal_path.write_text(json.dumps(_valid_tool_proposal()), encoding="utf-8")
    evidence_path = tmp_path / "evidence.txt"
    evidence_path.write_text("uv run pytest ... exit_code: 0", encoding="utf-8")

    scaffold = _run_cli(
        "agent-tools",
        "scaffold",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(proposal_path),
        "--json",
    )
    register = _run_cli(
        "agent-tools",
        "register",
        "--profile-root",
        str(tmp_path),
        "--id",
        "attendance-risk",
        "--json",
    )
    promote = _run_cli(
        "agent-tools",
        "promote",
        "--profile-root",
        str(tmp_path),
        "--id",
        "attendance-risk",
        "--evidence",
        str(evidence_path),
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
    assert register.returncode == 0, register.stderr
    assert promote.returncode == 0, promote.stderr
    assert explain.returncode == 0, explain.stderr
    assert deprecate.returncode == 0, deprecate.stderr
    assert json.loads(scaffold.stdout)["lifecycle_state"] == "draft"
    assert json.loads(register.stdout)["lifecycle_state"] == "registered"
    assert json.loads(promote.stdout)["lifecycle_state"] == "active"
    explain_payload = json.loads(explain.stdout)
    assert explain_payload["tool"]["id"] == "attendance-risk"
    assert explain_payload["tool"]["memory_obligation"]["key"] == "tool:attendance-risk"
    assert json.loads(deprecate.stdout)["lifecycle_state"] == "deprecated"


def test_draft_to_active_jump_rejected(tmp_path: Path) -> None:
    # Given: a freshly scaffolded draft tool.
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
    assert scaffold.returncode == 0, scaffold.stderr

    # When: promote is attempted straight from draft.
    result = _run_cli(
        "agent-tools",
        "promote",
        "--profile-root",
        str(tmp_path),
        "--id",
        "attendance-risk",
        "--evidence",
        "evidence.txt",
        "--json",
    )

    # Then: the jump is rejected with a typed transition error.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "INVALID_LIFECYCLE_TRANSITION"
    assert payload["from_state"] == "draft"
    assert payload["to_state"] == "active"


def test_promote_requires_evidence(tmp_path: Path) -> None:
    # Given: a registered tool.
    proposal_path = tmp_path / "valid-tool.json"
    proposal_path.write_text(json.dumps(_valid_tool_proposal()), encoding="utf-8")
    assert _run_cli(
        "agent-tools",
        "scaffold",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(proposal_path),
        "--json",
    ).returncode == 0
    assert _run_cli(
        "agent-tools",
        "register",
        "--profile-root",
        str(tmp_path),
        "--id",
        "attendance-risk",
        "--json",
    ).returncode == 0

    # When: promote runs without evidence.
    result = _run_cli(
        "agent-tools",
        "promote",
        "--profile-root",
        str(tmp_path),
        "--id",
        "attendance-risk",
        "--json",
    )

    # Then: the promotion is refused.
    assert result.returncode == 2, result.stdout
    assert json.loads(result.stdout)["error_code"] == "MISSING_PROMOTE_EVIDENCE"


def test_deprecated_tool_cannot_revive(tmp_path: Path) -> None:
    # Given: a deprecated tool.
    proposal_path = tmp_path / "valid-tool.json"
    proposal_path.write_text(json.dumps(_valid_tool_proposal()), encoding="utf-8")
    assert _run_cli(
        "agent-tools",
        "scaffold",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(proposal_path),
        "--json",
    ).returncode == 0
    assert _run_cli(
        "agent-tools",
        "deprecate",
        "--profile-root",
        str(tmp_path),
        "--id",
        "attendance-risk",
        "--json",
    ).returncode == 0

    # When: any revival transition is attempted.
    result = _run_cli(
        "agent-tools",
        "register",
        "--profile-root",
        str(tmp_path),
        "--id",
        "attendance-risk",
        "--json",
    )

    # Then: deprecated is terminal.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "INVALID_LIFECYCLE_TRANSITION"
    assert payload["from_state"] == "deprecated"


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
        "reuse_review": {
            "checked_existing": ["agent-tools list", "context hydrate"],
            "custom_build_justification": "Synthetic attendance risk is a reusable tool.",
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
