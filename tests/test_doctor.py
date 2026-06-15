from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def test_doctor_json_contract_passes_on_fresh_repo() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = _run_module(repo_root, "doctor", "--repair", "--json")

    assert result.returncode == 0, result.stderr
    payload = _json_object(result.stdout)
    assert payload["status"] in {"PASS", "REPAIRED"}
    assert payload["exit_code"] == 0
    assert _check_ids(payload) >= {"package", "plugin", "skills"}


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
    warning_message = warning_check["message_ko"]
    assert isinstance(warning_message, str)
    assert "broken-route.json" in warning_message
    assert "broken-route.json" in str(warning_check["repair_action"])
    assert str(tmp_path) not in result.stdout


def test_doctor_reports_installed_viewer_verify_evidence_age(tmp_path: Path) -> None:
    # Given: a profile has an installed generated viewer with stale verifier evidence.
    profile_root = tmp_path / "profile"
    viewer = profile_root / "codex-workspace" / "scripts" / "class_overview_view.html"
    viewer.parent.mkdir(parents=True)
    _ = viewer.write_text("<!doctype html><html><body>viewer</body></html>\n", encoding="utf-8")
    state_dir = profile_root / ".chat-lms-state"
    state_dir.mkdir(parents=True)
    _ = (state_dir / "side-panel-design-viewers.json").write_text(
        json.dumps(
            {
                "viewers": {
                    "class_overview": {
                        "block_id": "design-class-overview-stale",
                        "viewer_path": str(viewer),
                        "backup_path": "",
                        "artifact_sha256": "stale-sha",
                        "verify_evidence_path": str(tmp_path / "missing-old-evidence.json"),
                        "verify_evidence_timestamp_utc": "2000-01-01T00:00:00+00:00",
                        "installed_at": "2000-01-01T00:00:00+00:00",
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # When: doctor checks the profile.
    result = _run_module(
        _repo_root(),
        "doctor",
        "--profile-root",
        str(profile_root),
        "--json",
    )

    # Then: the verify-evidence row reports the stale state with a verifier repair action.
    assert result.returncode == 0, result.stdout
    check = _checks_by_id(result)["side_panel_viewers_verify_evidence"]
    assert check["status"] == "FAIL"
    message = check["message_ko"]
    assert isinstance(message, str)
    assert "stale" in message
    assert "side-panel design verify" in str(check["repair_action"])
    assert "--view class_overview" in str(check["repair_action"])
    assert str(profile_root) not in result.stdout


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _checks_by_id(
    result: subprocess.CompletedProcess[str],
) -> dict[str, dict[str, JsonValue]]:
    payload = _json_object(result.stdout)
    raw_checks = payload["checks"]
    assert isinstance(raw_checks, list)
    checks: dict[str, dict[str, JsonValue]] = {}
    for item in raw_checks:
        if not isinstance(item, dict):
            continue
        check = cast("dict[str, JsonValue]", item)
        check_id = check.get("id")
        if isinstance(check_id, str):
            checks[check_id] = check
    return checks


def _check_ids(payload: dict[str, JsonValue]) -> set[str]:
    raw_checks = payload["checks"]
    assert isinstance(raw_checks, list)
    ids: set[str] = set()
    for item in raw_checks:
        if not isinstance(item, dict):
            continue
        check = cast("dict[str, JsonValue]", item)
        check_id = check.get("id")
        if isinstance(check_id, str):
            ids.add(check_id)
    return ids


def _json_object(value: str | JsonValue) -> dict[str, JsonValue]:
    payload = cast("JsonValue", json.loads(value)) if isinstance(value, str) else value
    assert isinstance(payload, dict)
    return payload


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
