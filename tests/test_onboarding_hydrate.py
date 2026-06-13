from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _bootstrap_source() -> str:
    return (_REPO_ROOT / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8")


def test_hydrate_template_has_db_gated_onboarding_section() -> None:
    source = _bootstrap_source()
    assert '$onboardingSection = if ($dbStatus -eq "missing")' in source
    assert "First-Run Onboarding" in source
    assert "$onboardingSection" in source


def test_onboarding_directive_points_to_deterministic_clis() -> None:
    source = _bootstrap_source()
    assert "academy-db record-types define" in source
    assert "academy-db import apply" in source
    assert "Never hand-author the DB JSON" in source


def test_onboarding_documented_in_data_contract() -> None:
    contract = (_REPO_ROOT / "docs" / "academy-data-contract.md").read_text(encoding="utf-8")
    assert "## Onboarding" in contract
    assert "record-types define" in contract
