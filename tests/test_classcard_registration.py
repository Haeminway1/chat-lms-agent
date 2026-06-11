from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.route_packs import load_route_packs


def test_classcard_is_in_static_registry() -> None:
    # Given/When: the agent-tools list (always-on hydration source).
    result = _run_cli("agent-tools", "list", "--json")

    # Then: classcard is advertised with its memory obligation.
    assert result.returncode == 0, result.stdout
    tools = {tool["id"]: tool for tool in json.loads(result.stdout)["tools"]}
    assert "classcard" in tools
    assert tools["classcard"]["kind"] == "browser_automation"
    assert "tool:classcard" in tools["classcard"]["memory_obligation"]


def test_reuse_check_matches_classcard_intent() -> None:
    # Given/When: a Korean classcard intent runs through the reuse gate.
    result = _run_cli("agent-tools", "reuse-check", "--intent", "클래스카드 업로드", "--json")

    # Then: reuse wins — the agent is steered to the existing tool, not a rebuild.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["decision"] == "reuse_existing"
    assert "classcard" in {match["id"] for match in payload["matches"]}


def test_repo_ships_classcard_route_pack() -> None:
    # Given: the repo-default route packs.
    packs, warnings = load_route_packs(_repo_root())

    # Then: the classcard trigger route ships and parses cleanly.
    assert warnings == []
    pack = next(pack for pack in packs if pack.pack_id == "classcard_upload")
    assert "클래스카드" in pack.required_tokens
    assert "classcard direct-upload" in pack.then_command


def test_db_flow_reports_phase_b_not_wired(tmp_path: Path) -> None:
    # Given/When: the DB-integrated flow is invoked.
    result = _run_cli(
        "classcard",
        "upload",
        "--student",
        "가상학생",
        "--class-url",
        "https://www.classcard.net/ClassMain/1",
        "--checkpoint",
        str(tmp_path / "cp.json"),
        "--json",
    )

    # Then: it fails honestly instead of half-running.
    assert result.returncode == 2, result.stdout
    assert json.loads(result.stdout)["error_code"] == "CLASSCARD_DB_FLOW_NOT_WIRED"


def test_login_without_credentials_prompts_once() -> None:
    # Given/When: login runs with no credentials.
    result = _run_cli("classcard", "login", "--json")

    # Then: the one-time setup is requested in Korean, not a crash.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "CLASSCARD_CREDENTIALS_REQUIRED"
    assert "로그인" in payload["message_ko"]


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
