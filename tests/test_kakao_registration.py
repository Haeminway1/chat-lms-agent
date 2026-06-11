from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.route_packs import load_route_packs


def test_registry_route_pack_and_doctor_advertise_kakao(tmp_path: Path) -> None:
    # Given/When: the public discovery surfaces are inspected.
    registry = _run_cli("agent-tools", "list", "--json")
    reuse = _run_cli("agent-tools", "reuse-check", "--intent", "카카오 채널 메시지", "--json")
    doctor = _run_cli("doctor", "--profile-root", str(tmp_path), "--json")
    packs, warnings = load_route_packs(_repo_root(), None)

    # Then: Kakao is advertised as approval-gated browser automation.
    assert registry.returncode == 0, registry.stdout
    tools = {tool["id"]: tool for tool in json.loads(registry.stdout)["tools"]}
    kakao = tools["kakao"]
    assert kakao["kind"] == "browser_automation"
    assert "tool:kakao" in kakao["memory_obligation"]
    assert "--approval-id" in json.dumps(kakao["command_contract"])
    assert reuse.returncode == 0, reuse.stdout
    matches = json.dumps(json.loads(reuse.stdout)["matches"], ensure_ascii=False)
    assert "kakao" in matches

    assert warnings == []
    route = next(pack for pack in packs if pack.pack_id == "kakao_channel")
    assert "카카오" in route.required_tokens
    assert "approval" in " ".join(route.must_not).lower()

    assert doctor.returncode == 0, doctor.stdout
    checks = {check["id"]: check for check in json.loads(doctor.stdout)["checks"]}
    assert checks["kakao"]["status"] == "PASS"
    assert "Kakao" in checks["kakao"]["message_ko"] or "카카오" in checks["kakao"]["message_ko"]


def test_kakao_module_imports_no_solapi_or_reseller_code() -> None:
    # Given: every public-safe Kakao module in this slice.
    module_names = (
        "chat_lms_agent.kakao_plan",
        "chat_lms_agent.kakao_channel_page",
        "chat_lms_agent.kakao_send",
        "chat_lms_agent.kakao_calibration",
        "chat_lms_agent.kakao_core",
        "chat_lms_agent.kakao_handlers",
    )

    # When/Then: modules import cleanly and contain no SMS vendor implementation.
    for module_name in module_names:
        module = importlib.import_module(module_name)
        module_file = module.__file__
        assert isinstance(module_file, str)
        source = Path(module_file).read_text(encoding="utf-8").lower()
        assert "solapi" not in source
        assert "reseller" not in source


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
