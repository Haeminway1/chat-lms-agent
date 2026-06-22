from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_agent_tools_list_exposes_memory_obligations() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    result = _run_cli(repo_root, "agent-tools", "list", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert isinstance(payload["memory_obligation"], str)

    tools = {tool["id"]: tool for tool in payload["tools"]}
    assert {"side-panel", "write-action", "outbound-sync"} <= set(tools)
    assert all(isinstance(tool["memory_obligation"], str) for tool in tools.values())
    write_action = tools["write-action"]
    assert write_action["kind"] == "database_workflow"
    assert write_action["status"] == "active"
    commands = write_action["command_contract"]["commands"]
    assert isinstance(commands, list)
    assert any("write-action roster" in str(command) for command in commands)
    assert any("write-action apply" in str(command) for command in commands)
    outbound_sync = tools["outbound-sync"]
    assert outbound_sync["kind"] == "external_sync_workflow"
    outbound_commands = outbound_sync["command_contract"]["commands"]
    assert any("daily-management journal-plan" in str(command) for command in outbound_commands)
    assert any(
        "daily-management sync" in str(command) and "--execute" in str(command)
        for command in outbound_commands
    )
    assert any("ledger record" in str(command) for command in outbound_commands)


def test_agent_tools_validate_reports_missing_proposal_contracts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    proposal_path = tmp_path / "malformed-agent-tool.json"
    proposal_path.write_text(
        json.dumps(
            {
                "id": "attendance-risk",
                "label": "Attendance risk finder",
                "summary": "Find synthetic attendance risk only.",
            },
        ),
        encoding="utf-8",
    )

    result = _run_cli(
        repo_root,
        "agent-tools",
        "validate",
        "--from",
        str(proposal_path),
        "--json",
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert {"MISSING_MEMORY_OBLIGATION", "MISSING_COMMAND_CONTRACT"} <= set(
        payload["errors"],
    )


def test_context_hydrate_includes_agent_tool_registry_policy() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    result = _run_cli(repo_root, "context", "hydrate", "--for-codex", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert "side_panel" in payload
    assert "agent_tools" in payload
    assert "memory_policy" in payload
    assert "tool_registry" in payload
    assert payload["tool_registry"]["memory_obligation"] == payload["memory_policy"][
        "registry_memory_obligation"
    ]


def test_doctor_reports_agent_tool_registry_check() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    result = _run_cli(repo_root, "doctor", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    checks = {check["id"]: check for check in payload["checks"]}
    assert checks["agent_tools"]["status"] == "PASS"


def _run_cli(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )
