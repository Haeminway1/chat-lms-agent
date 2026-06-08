from __future__ import annotations

from pathlib import Path

REQUIRED_SKILLS = (
    "chat-lms-onboarding",
    "chat-lms-qa",
)


def test_required_skills_have_skill_md() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    missing = [
        skill
        for skill in REQUIRED_SKILLS
        if not (repo_root / ".agents" / "skills" / skill / "SKILL.md").exists()
    ]

    assert missing == []


def test_skill_frontmatter_has_name_and_description() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    for skill in REQUIRED_SKILLS:
        content = (repo_root / ".agents" / "skills" / skill / "SKILL.md").read_text(
            encoding="utf-8",
        )
        assert content.startswith("---\n")
        assert f"name: {skill}" in content
        assert "description:" in content
