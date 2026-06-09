from __future__ import annotations

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

    deprecated_terms = ("right panel", "assistant panel", "html panel", "우측패널")
    assert all(term not in before_notes for term in deprecated_terms)


def test_golden_standard_sections_name_source_or_assumption() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    standards = (repo_root / "docs" / "golden-standards.md").read_text(
        encoding="utf-8",
    )

    required_sections = ("lazycodex", "가제코드", "OMC", "OMX", "Hermes Agent")
    for section_name in required_sections:
        section = _markdown_section(standards, section_name)
        assert "- Adopted trait:" in section
        assert "- Local mapping:" in section
        assert ("- Source:" in section) or ("- Assumption:" in section)
        assert "- Must not copy:" in section
        assert "- Evidence:" in section


def _markdown_section(markdown: str, section_name: str) -> str:
    marker = f"## {section_name}"
    assert marker in markdown
    tail = markdown.split(marker, maxsplit=1)[1]
    return tail.split("\n## ", maxsplit=1)[0]
