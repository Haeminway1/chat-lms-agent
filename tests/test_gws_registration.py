"""gws must be discoverable: registry, reuse-check, route packs, doctor."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.route_packs import load_route_packs, match_pack_route


def test_registry_advertises_gws_with_memory_obligation() -> None:
    result = _run_cli("agent-tools", "list", "--json")

    assert result.returncode == 0, result.stdout
    tools = {tool["id"]: tool for tool in json.loads(result.stdout)["tools"]}
    gws = tools["gws"]
    assert gws["kind"] == "external_api"
    assert "tool:gws" in gws["memory_obligation"]
    commands = json.dumps(gws["command_contract"], ensure_ascii=False)
    assert "gws calendar list" in commands
    assert "gws gmail send" in commands
    assert "--approval-id" in commands


def test_reuse_check_matches_korean_workspace_intents(tmp_path: Path) -> None:
    for intent in ("캘린더 일정 등록", "단어시험지 구글 시트로 올리기"):
        result = _run_cli(
            "agent-tools",
            "reuse-check",
            "--intent",
            intent,
            "--profile-root",
            str(tmp_path),
            "--json",
        )
        assert result.returncode == 0, result.stdout
        payload = json.loads(result.stdout)
        matches = json.dumps(payload.get("matches", []), ensure_ascii=False)
        assert "gws" in matches, f"intent {intent} did not match gws: {matches}"


def test_route_packs_ship_gws_triggers_with_browser_ban() -> None:
    packs, warnings = load_route_packs(_repo_root(), None)

    assert not warnings
    by_id = {pack.pack_id: pack for pack in packs}
    for pack_id in ("gws_calendar", "gws_schedule", "gws_upload"):
        assert pack_id in by_id, f"missing route pack {pack_id}"
        assert any("browser" in rule for rule in by_id[pack_id].must_not)
    assert any("teacher approval" in rule for rule in by_id["gws_upload"].must_not)
    schedule = match_pack_route(packs, "내일 수업 일정 등록해줘")
    assert schedule is not None
    assert schedule.pack_id == "gws_schedule"
    upload = match_pack_route(packs, "이번 주 단어시험지 시트로 올려줘")
    assert upload is not None
    assert upload.pack_id == "gws_upload"


def test_doctor_reports_gws_advisory_without_failing(tmp_path: Path) -> None:
    result = _run_cli("doctor", "--profile-root", str(tmp_path), "--json")

    payload = json.loads(result.stdout)
    checks = {check["id"]: check for check in payload["checks"]}
    assert "gws" in checks
    assert checks["gws"]["status"] == "PASS"
    assert "gws" in checks["gws"]["message_ko"] or "Workspace" in checks["gws"]["message_ko"]


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
        input="",
    )
