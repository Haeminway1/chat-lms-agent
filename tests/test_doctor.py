from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def test_doctor_json_contract_passes_on_fresh_repo() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_module(repo_root, "doctor", "--repair", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] in {"PASS", "REPAIRED"}
    assert payload["exit_code"] == 0
    assert isinstance(payload["checks"], list)
    assert {check["id"] for check in payload["checks"]} >= {"package", "plugin", "skills"}


def test_doctor_redacts_credentials() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["GOOGLE_" + "CLIENT_SECRET"] = "secret-value-that-must-not-leak"

    result = subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", "doctor", "--repair", "--json"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "secret-value-that-must-not-leak" not in result.stdout


def test_doctor_reports_lesson_panel_assets_missing_then_installed(
    tmp_path: Path,
) -> None:
    # Given: a private profile starts without user-owned lesson panel assets.
    profile_root = tmp_path / "profile"
    profile_root.mkdir()

    # When: doctor runs before and after installing the lesson panel assets.
    missing = _run_module(
        _repo_root(),
        "doctor",
        "--profile-root",
        str(profile_root),
        "--json",
    )
    installed = _run_module(
        _repo_root(),
        "side-panel",
        "lesson",
        "install-assets",
        "--profile-root",
        str(profile_root),
        "--json",
    )
    present = _run_module(
        _repo_root(),
        "doctor",
        "--profile-root",
        str(profile_root),
        "--json",
    )

    # Then: doctor exposes the repairable asset row and flips it to PASS.
    assert missing.returncode == 0, missing.stdout
    assert installed.returncode == 0, installed.stdout
    assert present.returncode == 0, present.stdout
    missing_check = _checks_by_id(missing)["lesson_panel_runtime_assets"]
    present_check = _checks_by_id(present)["lesson_panel_runtime_assets"]
    assert missing_check["status"] == "FAIL"
    assert "side-panel lesson install-assets" in str(missing_check["repair_action"])
    assert present_check["status"] == "PASS"


def test_doctor_reports_malformed_profile_route_pack_warning(tmp_path: Path) -> None:
    # Given: a private profile has one malformed route pack file.
    routes_dir = tmp_path / ".chat-lms-state" / "routes"
    routes_dir.mkdir(parents=True)
    _ = (routes_dir / "broken-route.json").write_text("{not-json", encoding="utf-8")

    # When: doctor checks the profile.
    result = _run_module(
        _repo_root(),
        "doctor",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: doctor surfaces the warning row without leaking private paths.
    assert result.returncode == 0, result.stdout
    warning_check = _checks_by_id(result)["route_pack_warnings"]
    assert warning_check["status"] == "FAIL"
    assert "broken-route.json" in warning_check["message_ko"]
    assert "broken-route.json" in str(warning_check["repair_action"])
    assert str(tmp_path) not in result.stdout


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _checks_by_id(
    result: subprocess.CompletedProcess[str],
) -> dict[str, dict[str, JsonValue]]:
    payload = json.loads(result.stdout)
    return {
        check["id"]: check
        for check in payload["checks"]
        if isinstance(check, dict) and isinstance(check.get("id"), str)
    }


def _run_module(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
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
