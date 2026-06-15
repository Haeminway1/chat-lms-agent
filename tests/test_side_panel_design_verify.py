from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from chat_lms_agent.side_panel import side_panel_view_draft
from chat_lms_agent.side_panel_design_verify_contract import (
    VerifyEvidenceParts,
    artifact_sha256,
    build_verify_evidence,
    build_verify_fixtures,
)

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:
    PlaywrightError = RuntimeError
    sync_playwright = None

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def _chromium_available() -> bool:
    if os.environ.get("CHAT_LMS_AGENT_DESIGN_VERIFY_DISABLE_BROWSER") == "1":
        return False
    if sync_playwright is None:
        return False
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            _ = browser.close()
    except PlaywrightError:
        return False
    return True


_CHROMIUM_AVAILABLE = _chromium_available()


def test_verify_fixtures_are_disjoint_and_cover_required_sections() -> None:
    # Given: the class overview view declares required sections.
    draft = side_panel_view_draft("class_overview")
    required_sections = _json_strings(draft["required_sections"])

    # When: verifier fixtures are built for that view.
    fixtures = build_verify_fixtures("class_overview")

    # Then: A/B markers are deterministic, disjoint, and cover each section.
    assert fixtures.fixture_a["synthetic"] is True
    assert fixtures.fixture_b["synthetic"] is True
    assert fixtures.markers_a
    assert fixtures.markers_b
    assert set(fixtures.markers_a).isdisjoint(set(fixtures.markers_b))
    for section in required_sections:
        assert any(section.upper() in marker for marker in fixtures.markers_a)
        assert any(section.upper() in marker for marker in fixtures.markers_b)


def test_verify_evidence_records_exact_artifact_sha256(tmp_path: Path) -> None:
    # Given: an artifact path and one passing check.
    artifact = tmp_path / "artifact.html"
    _ = artifact.write_text("<!doctype html><html><body>one</body></html>\n", encoding="utf-8")

    # When: evidence is built for the artifact.
    evidence = build_verify_evidence(
        VerifyEvidenceParts(
            artifact_path=artifact,
            view="class_overview",
            mode="panel",
            checked_modes=("panel",),
            lint_payload={"status": "PASS", "errors": []},
            checks=[{"id": "fixture_a_markers", "status": "PASS"}],
        ),
    )

    # Then: the hash matches exact bytes and changes when the artifact changes.
    assert evidence["artifact_sha256"] == artifact_sha256(artifact)
    first_hash = evidence["artifact_sha256"]
    _ = artifact.write_text("<!doctype html><html><body>two</body></html>\n", encoding="utf-8")
    assert artifact_sha256(artifact) != first_hash


@pytest.mark.skipif(not _CHROMIUM_AVAILABLE, reason="Playwright chromium is not installed")
def test_design_verify_cli_passes_data_bound_artifact() -> None:
    # Given: a lint-compliant artifact renders data from /api/lesson-panel.
    artifact = _fixture("data-bound.html")

    # When: the verifier drives the artifact through Playwright.
    result = _run_cli(
        "side-panel",
        "design",
        "verify",
        "--artifact",
        str(artifact),
        "--view",
        "class_overview",
        "--mode",
        "all",
        "--json",
    )

    # Then: both fixtures bind and both declared viewport modes avoid horizontal scroll.
    assert result.returncode == 0, result.stdout
    payload = _json_object(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["schema_version"] == "side-panel-design-verify-evidence-v1"
    assert payload["spec_version"] == "display-spec-v1"
    assert payload["view"] == "class_overview"
    assert payload["mode"] == "all"
    assert payload["checked_modes"] == ["panel", "fullscreen"]
    assert re.fullmatch(r"[0-9a-f]{64}", _json_string(payload["artifact_sha256"]))
    checks = _checks_by_id(payload)
    assert checks["fixture_a_markers"]["status"] == "PASS"
    assert checks["fixture_b_replaces_a"]["status"] == "PASS"
    assert checks["panel_horizontal_scroll"]["status"] == "PASS"
    assert checks["fullscreen_horizontal_scroll"]["status"] == "PASS"


@pytest.mark.skipif(not _CHROMIUM_AVAILABLE, reason="Playwright chromium is not installed")
def test_design_verify_rejects_hardcoded_data_after_fixture_swap() -> None:
    # Given: a lint-compliant artifact fetches /api/ but renders hardcoded A fixture text.
    artifact = _fixture("hardcoded-data.html")

    # When: the verifier swaps from fixture A to fixture B.
    result = _run_cli(
        "side-panel",
        "design",
        "verify",
        "--artifact",
        str(artifact),
        "--view",
        "class_overview",
        "--mode",
        "panel",
        "--json",
    )

    # Then: the fixture-swap check fails because B markers never appear.
    assert result.returncode == 2, result.stdout
    payload = _json_object(result.stdout)
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "DESIGN_VERIFY_FAILED"
    failed = _failed_checks(payload)
    assert "fixture_b_replaces_a" in failed


@pytest.mark.skipif(not _CHROMIUM_AVAILABLE, reason="Playwright chromium is not installed")
def test_design_verify_rejects_panel_horizontal_scroll() -> None:
    # Given: a data-bound artifact creates runtime content wider than panel mode.
    artifact = _fixture("horizontal-scroll-runtime.html")

    # When: the verifier checks panel dimensions.
    result = _run_cli(
        "side-panel",
        "design",
        "verify",
        "--artifact",
        str(artifact),
        "--view",
        "class_overview",
        "--mode",
        "panel",
        "--json",
    )

    # Then: panel horizontal scroll is reported with the measured viewport.
    assert result.returncode == 2, result.stdout
    payload = _json_object(result.stdout)
    checks = _checks_by_id(payload)
    panel_check = checks["panel_horizontal_scroll"]
    assert panel_check["status"] == "FAIL"
    assert _json_object(panel_check["viewport"]) == {"width": 372, "height": 760}


def test_design_verify_runtime_missing_returns_blocked() -> None:
    # Given: the runtime guard simulates a missing Playwright/browser runtime.
    artifact = _fixture("data-bound.html")

    # When: verify runs with the guard enabled.
    result = _run_cli(
        "side-panel",
        "design",
        "verify",
        "--artifact",
        str(artifact),
        "--view",
        "class_overview",
        "--json",
        env_extra={"CHAT_LMS_AGENT_DESIGN_VERIFY_DISABLE_BROWSER": "1"},
    )

    # Then: a typed BLOCKED payload is returned without a traceback.
    assert result.returncode == 5, result.stdout
    payload = _json_object(result.stdout)
    assert payload["status"] == "BLOCKED"
    assert payload["error_code"] == "DESIGN_VERIFY_RUNTIME_MISSING"
    assert "playwright install chromium" in _json_string(payload["install_hint"])
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr


def _fixture(name: str) -> Path:
    return _repo_root() / "tests" / "fixtures" / "side_panel_design_verify" / name


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(
    *args: str,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    if env_extra is not None:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        input="",
        capture_output=True,
        check=False,
        text=True,
    )


def _json_object(value: str | JsonValue) -> dict[str, JsonValue]:
    payload = cast("JsonValue", json.loads(value)) if isinstance(value, str) else value
    assert isinstance(payload, dict)
    return payload


def _json_string(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _json_strings(value: JsonValue) -> list[str]:
    assert isinstance(value, list)
    return [item for item in value if isinstance(item, str)]


def _checks_by_id(payload: dict[str, JsonValue]) -> dict[str, dict[str, JsonValue]]:
    checks = payload["checks"]
    assert isinstance(checks, list)
    by_id: dict[str, dict[str, JsonValue]] = {}
    for item in checks:
        if not isinstance(item, dict):
            continue
        check = cast("dict[str, JsonValue]", item)
        check_id = check.get("id")
        if isinstance(check_id, str):
            by_id[check_id] = check
    return by_id


def _failed_checks(payload: dict[str, JsonValue]) -> set[str]:
    return {
        check_id
        for check_id, check in _checks_by_id(payload).items()
        if check.get("status") == "FAIL"
    }
