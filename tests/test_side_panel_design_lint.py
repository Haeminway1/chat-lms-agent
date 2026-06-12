from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

    import pytest

from chat_lms_agent import side_panel_design_lint as lint_module

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def test_display_spec_v1_matches_design_reference() -> None:
    # Given: the design reference documents the required panel shell and token axis.
    repo_root = _repo_root()
    reference = (repo_root / "docs" / "side-panel-design-reference.md").read_text(
        encoding="utf-8",
    )

    # When: the machine-readable display spec is parsed.
    spec = _json_object(
        (repo_root / "assets" / "side-panel" / "display-spec-v1.json").read_text(
            encoding="utf-8",
        ),
    )

    # Then: DS1 values match the documented reference instead of drifting.
    assert "372px x 760px" in reference
    assert "## Display Spec v1" in reference
    assert "Density, roundness, accent, theme, and font size token axes" in reference
    assert spec["schema_version"] == "display-spec-v1"
    modes = _json_object(spec["modes"])
    assert set(modes) == {"panel", "fullscreen"}
    assert modes["panel"] == {
        "base_viewport": {"width": 372, "height": 760},
        "width_band": {"min": 360, "max": 480},
        "columns": "single",
        "horizontal_scroll": "forbidden",
        "vertical_scroll": "allowed",
        "touch_target_min_px": 44,
        "font_size": {"token_axis": "fontSize", "min": 13, "max": 18},
    }
    assert modes["fullscreen"] == {
        "min_viewport": {"width": 1024, "height": 768},
        "columns": "multi",
        "horizontal_scroll": "forbidden",
        "horizontal_scroll_scope": "document",
    }


def test_design_lint_cli_accepts_compliant_panel_fixture() -> None:
    # Given: a panel-only HTML fixture satisfying DS2.
    artifact = _fixture("compliant-panel.html")

    # When: the design lint CLI runs in panel mode.
    result = _run_cli(
        "side-panel",
        "design",
        "lint",
        "--artifact",
        str(artifact),
        "--mode",
        "panel",
        "--json",
    )

    # Then: it passes with the validation-style JSON contract.
    assert result.returncode == 0, result.stdout
    payload = _json_object(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["mode"] == "panel"
    assert payload["errors"] == []


def test_design_lint_cli_rejects_horizontal_scroll_fixture() -> None:
    _assert_lint_fails(
        "horizontal-scroll.html",
        expected_error="overflow-x:auto is forbidden on body",
    )


def test_design_lint_cli_rejects_fixed_width_720_in_panel_mode() -> None:
    _assert_lint_fails(
        "fixed-width-720.html",
        expected_error="fixed width 720px exceeds panel max width 480px on .shell",
    )


def test_design_lint_cli_rejects_missing_modes_meta() -> None:
    _assert_lint_fails(
        "missing-modes-meta.html",
        expected_error="missing side-panel-modes meta",
    )


def test_design_lint_cli_rejects_external_cdn_stylesheet() -> None:
    _assert_lint_fails(
        "external-cdn.html",
        expected_error="external http(s) reference is forbidden",
    )


def test_design_lint_cli_rejects_missing_relative_api_fetch() -> None:
    _assert_lint_fails(
        "missing-api-fetch.html",
        expected_error="missing fetch call targeting a relative /api/ path",
    )


def test_design_lint_cli_rejects_missing_dark_theme_block() -> None:
    _assert_lint_fails(
        "missing-dark-theme.html",
        expected_error="missing dark theme block",
    )


def test_design_lint_cli_checks_fullscreen_declared_artifact_against_fullscreen_rules() -> None:
    # Given: one artifact declares both panel and fullscreen support.
    artifact = _fixture("fullscreen-responsive.html")

    # When: lint runs over every declared mode.
    result = _run_cli(
        "side-panel",
        "design",
        "lint",
        "--artifact",
        str(artifact),
        "--mode",
        "all",
        "--json",
    )

    # Then: both panel and fullscreen results are reported and pass.
    assert result.returncode == 0, result.stdout
    payload = _json_object(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["mode"] == "all"
    assert payload["checked_modes"] == ["panel", "fullscreen"]
    assert payload["errors"] == []


def test_repo_lesson_template_lints_for_panel_and_fullscreen_modes() -> None:
    # Given: the repository lesson-panel template is the source for user installs.
    artifact = _repo_root() / "assets" / "side-panel" / "lesson_panel_view.html"

    # When: lint runs over every declared mode.
    result = _run_cli(
        "side-panel",
        "design",
        "lint",
        "--artifact",
        str(artifact),
        "--mode",
        "all",
        "--json",
    )

    # Then: the template passes both panel and fullscreen design rules.
    assert result.returncode == 0, result.stdout
    payload = _json_object(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["checked_modes"] == ["panel", "fullscreen"]


def test_design_lint_accepts_empty_impeccable_array_without_changing_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: impeccable is locally available and reports the real empty JSON array shape.
    calls: list[Sequence[str]] = []

    def fake_run(
        args: Sequence[str],
        *,
        capture_output: bool,
        check: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        assert capture_output is True
        assert check is False
        assert text is True
        assert timeout > 0
        return subprocess.CompletedProcess([*args], 0, stdout="[]", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # When: the core lint passes.
    code, payload = lint_module.side_panel_design_lint(_fixture("compliant-panel.html"), "panel")

    # Then: lint still passes and impeccable exposes an empty findings list.
    assert code == 0
    assert payload["status"] == "PASS"
    advisory = _json_object(payload["advisory"])
    impeccable = _json_object(advisory["impeccable"])
    assert impeccable["status"] == "PASS"
    assert impeccable["findings"] == []
    assert calls == [
        (
            "npx",
            "--no-install",
            "impeccable@2.3.2",
            "detect",
            str(_fixture("compliant-panel.html")),
            "--fast",
            "--json",
        ),
    ]


def test_design_lint_attaches_impeccable_findings_exit_two_without_changing_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: impeccable reports findings with the real array JSON shape and exit 2.
    def fake_run(
        args: Sequence[str],
        *,
        capture_output: bool,
        check: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output is True
        assert check is False
        assert text is True
        assert timeout > 0
        stdout = json.dumps(
            [
                {
                    "rule_id": "spacing-density",
                    "severity": "warning",
                    "message": "Spacing is too tight.",
                },
            ],
        )
        return subprocess.CompletedProcess([*args], 2, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    # When: the core lint passes.
    code, payload = lint_module.side_panel_design_lint(_fixture("compliant-panel.html"), "panel")

    # Then: lint still passes and advisory findings are preserved.
    assert code == 0
    assert payload["status"] == "PASS"
    advisory = _json_object(payload["advisory"])
    impeccable = _json_object(advisory["impeccable"])
    assert impeccable["status"] == "FINDINGS"
    assert impeccable["findings"] == [
        {
            "rule_id": "spacing-density",
            "severity": "warning",
            "message": "Spacing is too tight.",
        },
    ]


def test_design_lint_impeccable_absent_is_skipped_without_changing_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the optional detector is absent.
    def fake_run(
        args: Sequence[str],
        *,
        capture_output: bool,
        check: bool,
        text: bool,
        timeout: float,
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output is True
        assert check is False
        assert text is True
        assert timeout > 0
        raise FileNotFoundError(args[0])

    monkeypatch.setattr(subprocess, "run", fake_run)

    # When: the core lint fails for display-spec reasons.
    code, payload = lint_module.side_panel_design_lint(_fixture("horizontal-scroll.html"), "all")

    # Then: the failure remains the display-spec failure and impeccable is advisory SKIPPED.
    assert code == 2
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "INVALID_SIDE_PANEL_DESIGN"
    advisory = _json_object(payload["advisory"])
    impeccable = _json_object(advisory["impeccable"])
    assert impeccable == {
        "status": "SKIPPED",
        "reason": "impeccable not installed",
        "install_hint": "npx impeccable skills install",
    }


def test_doctor_reports_installed_profile_viewer_design_lint_status(tmp_path: Path) -> None:
    # Given: profile viewer assets are installed from the current repo template.
    profile_root = tmp_path / "profile"
    install = _run_cli(
        "side-panel",
        "lesson",
        "install-assets",
        "--profile-root",
        str(profile_root),
        "--json",
    )

    # When: doctor runs in profile mode.
    doctor = _run_cli("doctor", "--profile-root", str(profile_root), "--json")

    # Then: the static design lint row reports the current template as compliant.
    assert install.returncode == 0, install.stdout
    assert doctor.returncode == 0, doctor.stdout
    check = _checks_by_id(doctor)["side_panel_viewers_lint"]
    assert check["status"] == "PASS"
    message = check["message_ko"]
    assert isinstance(message, str)
    assert "pass design lint" in message
    assert check["repair_action"] is None
    assert str(profile_root) not in doctor.stdout


def _assert_lint_fails(fixture_name: str, *, expected_error: str) -> None:
    result = _run_cli(
        "side-panel",
        "design",
        "lint",
        "--artifact",
        str(_fixture(fixture_name)),
        "--json",
    )

    assert result.returncode == 2, result.stdout
    payload = _json_object(result.stdout)
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "INVALID_SIDE_PANEL_DESIGN"
    errors = payload["errors"]
    assert isinstance(errors, list)
    assert any(isinstance(error, str) and expected_error in error for error in errors)


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


def _fixture(name: str) -> Path:
    return _repo_root() / "tests" / "fixtures" / "side_panel_design_lint" / name


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
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
