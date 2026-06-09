from __future__ import annotations

from pathlib import Path


def test_design_reference_documents_zip_derived_required_blocks() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    reference = (repo_root / "docs" / "side-panel-design-reference.md").read_text(
        encoding="utf-8",
    )

    assert "372px x 760px" in reference
    assert "Warning-first" in reference or "Warning-first".lower() in reference.lower()
    assert "source command footer" in reference.lower()
    assert "class_overview" in reference


def test_building_block_catalog_defines_agent_and_user_ownership() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    catalog = (repo_root / "docs" / "side-panel-building-block-catalog.md").read_text(
        encoding="utf-8",
    )

    assert "SidePanelShell" in catalog
    assert "ActionGroup" in catalog
    assert "Agent-owned contract" in catalog
    assert "User-owned visual area" in catalog


def test_user_owned_html_css_boundary_is_explicit() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    boundary = (repo_root / "docs" / "side-panel-user-owned-html-css.md").read_text(
        encoding="utf-8",
    )

    assert "Create standalone side-panel HTML from scratch" in boundary
    assert "Validate payloads" in boundary
    assert "source_commands" in boundary


def test_terminology_names_side_panel_as_official_surface() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    terminology = (repo_root / "docs" / "terminology.md").read_text(encoding="utf-8")

    assert "보조 패널(side panel)" in terminology
    assert "CLI namespace: `side-panel`" in terminology
