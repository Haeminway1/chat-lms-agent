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
    assert payload["checked"]["agent_tool_count"] >= 2
    assert payload["checked"]["skill_count"] >= 2
    assert payload["checked"]["oss_candidate_count"] >= 1


def test_reuse_check_finds_wordbook_side_panel_for_korean_panel_intent() -> None:
    # Given: a synthetic Korean learner command asking to open the wordbook HTML panel.
    # When: the agent runs the reuse-before-build gate.
    result = _run_cli(
        "agent-tools",
        "reuse-check",
        "--intent",
        "가상학생 단어 html 패널 열어줘",
        "--json",
    )

    # Then: the reusable side-panel wordbook route is selected before file search.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "reuse_existing"
    matches = {match["id"]: match for match in payload["matches"]}
    commands = matches["side-panel"]["command_contract"]["commands"]
    assert any("side-panel wordbook open-plan" in command for command in commands)


def test_reuse_check_finds_wordbook_side_panel_for_korean_status_report() -> None:
    # Given: a realistic teacher prompt asking for an existing learner word status report.
    result = _run_cli(
        "agent-tools",
        "reuse-check",
        "--intent",
        "과외 가상학생 학생 단어 현황 보고",
        "--json",
    )

    # Then: reuse wins before any custom report or DB rebuild path.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "reuse_existing"
    matches = {match["id"]: match for match in payload["matches"]}
    commands = matches["side-panel"]["command_contract"]["commands"]
    assert any("agent-tools prompt-check" in command for command in commands)
    assert any("side-panel wordbook open-plan" in command for command in commands)


def test_prompt_check_routes_wordbook_status_without_profile() -> None:
    # Given: the exact shape a teacher can paste into a new session.
    result = _run_cli(
        "agent-tools",
        "prompt-check",
        "--prompt",
        "과외 가상학생 학생 단어 현황 보고",
        "--json",
    )

    # Then: the harness emits a route plan, not a build plan.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "use_existing_route"
    assert payload["student_hint"] == "가상학생"
    assert payload["acceptance"]["first_gate_under_5000_ms"] is True
    assert payload["route"]["first_command"].startswith("agent-tools prompt-check")
    assert '--student "가상학생"' in payload["route"]["then_command"]
    assert payload["route"]["then_command"].startswith("side-panel wordbook open-plan")
    assert "do not create a new HTML report for this request" in payload["route"]["must_not"]


def test_reuse_check_matches_short_db_token_and_reports_scanned_sources() -> None:
    # Given: a short but common academy database intent.
    result = _run_cli(
        "agent-tools",
        "reuse-check",
        "--intent",
        "build DB import",
        "--json",
    )

    # When/Then: the DB token still matches the academy DB surface.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "reuse_existing"
    assert "academy-db" in {match["id"] for match in payload["matches"]}
    assert payload["checked"]["agent_tool_count"] >= 2
    assert payload["checked"]["skill_count"] >= 2


def test_reuse_check_can_scan_sources_without_matches() -> None:
    # Given: an intent that does not match current reusable surfaces.
    result = _run_cli(
        "agent-tools",
        "reuse-check",
        "--intent",
        "build unrelated payroll importer",
        "--json",
    )

    # When/Then: checked sources are honest inventory counts, not match claims.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["decision"] == "custom_build_allowed_after_review"
    assert payload["matches"] == []
    assert payload["checked"]["existing_skills"] is True
    assert payload["checked"]["skill_count"] >= 2


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
