from __future__ import annotations

import json
from pathlib import Path


def test_side_panel_terminology_is_locked() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    terminology = (repo_root / "docs" / "terminology.md").read_text(encoding="utf-8")

    assert "## 보조 패널(side panel)" in terminology
    assert "Official Korean name: `보조 패널`" in terminology
    assert "Official bilingual name: `보조 패널(side panel)`" in terminology
    assert "CLI namespace: `side-panel`" in terminology


def test_deprecated_panel_terms_are_confined_to_migration_notes() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    terminology = (repo_root / "docs" / "terminology.md").read_text(encoding="utf-8")

    deprecated_heading = "## Deprecated Term Notes"
    assert deprecated_heading in terminology
    before_notes = terminology.split(deprecated_heading, maxsplit=1)[0]

    deprecated_terms = ("right panel", "assistant panel", "html panel", "우측 패널")
    assert all(term not in before_notes for term in deprecated_terms)


def test_golden_standard_sections_name_source_or_assumption() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    standards = (repo_root / "docs" / "golden-standards.md").read_text(
        encoding="utf-8",
    )

    required_sections = ("lazycodex", "gajae-code", "OMC", "OMX", "Hermes Agent")
    for section_name in required_sections:
        section = _markdown_section(standards, section_name)
        assert "- Adopted trait:" in section
        assert "- Local mapping:" in section
        assert ("- Source:" in section) or ("- Assumption:" in section)
        assert "- Must not copy:" in section
        assert "- Evidence:" in section


def test_oss_reference_registry_is_canonical_and_source_pinned() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    registry_path = repo_root / "docs" / "oss-reference-registry.md"
    registry = registry_path.read_text(encoding="utf-8")
    standards = (repo_root / "docs" / "golden-standards.md").read_text(
        encoding="utf-8",
    )

    assert "docs/oss-reference-registry.md" in standards
    assert "媛" not in standards
    assert "�" not in standards

    payload = _json_block(registry)
    entries = payload["references"]
    assert isinstance(entries, list)
    required_keys = {
        "id",
        "source_url",
        "pinned_head_sha",
        "observed_at",
        "license",
        "popularity_signal",
        "local_problem_matched",
        "adoption_status",
        "local_mapping",
        "must_not_copy",
        "privacy_boundary",
        "freshness_note",
    }
    by_id = {
        entry["id"]: entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }
    assert {
        "agents-md",
        "agent-skills",
        "headroom",
        "tencentdb-agent-memory",
        "roach-pi",
    } <= set(by_id)
    for entry in by_id.values():
        assert required_keys <= set(entry)
    for reference_id in (
        "agents-md",
        "agent-skills",
        "headroom",
        "tencentdb-agent-memory",
        "roach-pi",
    ):
        entry = by_id[reference_id]
        assert entry["observed_at"] == "2026-06-09"
        assert entry["adoption_status"] in {
            "direct-now",
            "candidate-next",
            "reference-only",
            "rejected",
        }
        assert entry["must_not_copy"]
        assert entry["privacy_boundary"]


def test_overview_docs_exist_and_stay_current() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    assert "Minimal Python package skeleton" not in readme, "README rotted again"
    assert "docs/architecture.md" in readme
    assert "PRD.md" in readme
    assert "plans/STATUS.md" in readme

    assert (repo_root / "PRD.md").exists()
    prd = (repo_root / "PRD.md").read_text(encoding="utf-8")
    assert "Codex Desktop" in prd
    assert "Non-goals" in prd

    architecture = (repo_root / "docs" / "architecture.md").read_text(encoding="utf-8")
    for anchor in (
        "hosts.py",
        "pre_tool_gate.py",
        "session_closeout",
        "model-catalog",
        "route_packs",
    ):
        assert anchor in architecture, anchor

    assert (repo_root / "plans" / "STATUS.md").exists()


def test_prompt_route_catalog_pipeline_docs_are_current() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    routes_readme = (repo_root / "routes" / "README.md").read_text(encoding="utf-8")
    assert "NO_MATCH Catalog Behavior" in routes_readme
    assert "route_catalog" in routes_readme
    assert "first_command" in routes_readme
    assert "avoid creating\nnew HTML" in routes_readme

    architecture = (repo_root / "docs" / "architecture.md").read_text(encoding="utf-8")
    assert "Natural-Language Panel Pipeline" in architecture
    assert "fixed CLI surface" in architecture
    assert "read-only `/api/lesson-panel`" in architecture

    status = (repo_root / "plans" / "STATUS.md").read_text(encoding="utf-8")
    assert "prompt-intent-routing-and-lesson-panel-plan.md" in status
    assert "Completed 2026-06-12" in status


def _markdown_section(markdown: str, section_name: str) -> str:
    marker = f"## {section_name}"
    assert marker in markdown
    tail = markdown.split(marker, maxsplit=1)[1]
    return tail.split("\n## ", maxsplit=1)[0]


def _json_block(markdown: str) -> dict[str, object]:
    marker = "```json"
    assert marker in markdown
    raw = markdown.split(marker, maxsplit=1)[1].split("```", maxsplit=1)[0]
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    return payload
