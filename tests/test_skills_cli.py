from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_skills_validate_lists_required_public_skills() -> None:
    # Given: Chat LMS public skills are stored in the repo.
    # When: validating the skill drawers through the CLI.
    result = _run_cli("skills", "validate", "--json")

    # Then: required reusable workflows are discoverable and valid.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert str(_repo_root()) not in result.stdout
    assert _repo_root().as_posix() not in result.stdout
    skill_ids = {skill["id"] for skill in payload["skills"]}
    assert {"chat-lms-onboarding", "chat-lms-qa"} <= skill_ids
    assert payload["private_data_found"] is False


def test_skills_list_includes_trigger_summary() -> None:
    # Given/When: listing the public skills through the CLI.
    result = _run_cli("skills", "list", "--json")

    # Then: each skill includes a short trigger summary alongside the path.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    skill_ids = {skill["id"]: skill for skill in payload["skills"]}
    assert "trigger_summary" in skill_ids["chat-lms-onboarding"]
    assert skill_ids["chat-lms-onboarding"]["trigger_summary"]


def test_skills_validate_rejects_malformed_custom_root(tmp_path: Path) -> None:
    # Given: a synthetic skill drawer with missing frontmatter.
    skill_root = tmp_path / "bad-skill"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text("# missing frontmatter\n", encoding="utf-8")

    # When: validating the custom root directly.
    result = _run_cli("skills", "validate", "--root", str(skill_root), "--json")

    # Then: validation fails with an exact missing-frontmatter error.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert "MISSING_SKILL_FRONTMATTER" in payload["errors"]


def test_skills_validate_rejects_bare_secret_and_windows_path(tmp_path: Path) -> None:
    # Given: a synthetic skill drawer containing private-looking values.
    skill_root = tmp_path / "leaky-skill"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text(
        "---\n"
        "name: leaky-skill\n"
        "description: Leaky skill for validation.\n"
        "---\n"
        "Use SECRET_TOKEN and C:\\Users\\haemi\\private-profile.\n",
        encoding="utf-8",
    )

    # When: validating the custom root directly.
    result = _run_cli("skills", "validate", "--root", str(skill_root), "--json")

    # Then: validation blocks broad secret tokens and local Windows paths.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert payload["private_data_found"] is True
    assert "PRIVATE_DATA_FOUND" in payload["errors"]


def test_skills_validate_rejects_bare_secret_identifier(tmp_path: Path) -> None:
    # Given: a synthetic skill drawer containing an uppercase secret identifier.
    skill_root = tmp_path / "bare-secret-skill"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text(
        "---\n"
        "name: bare-secret-skill\n"
        "description: Bare secret validation.\n"
        "---\n"
        "The runtime marker is SECRET_TOKEN.\n",
        encoding="utf-8",
    )

    # When: validating the custom root directly.
    result = _run_cli("skills", "validate", "--root", str(skill_root), "--json")

    # Then: validation blocks uppercase secret identifiers even without equals signs.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert "PRIVATE_DATA_FOUND" in payload["errors"]


def test_skills_validate_redacts_private_frontmatter_on_failure(tmp_path: Path) -> None:
    # Given: a malformed public skill whose frontmatter contains private-looking values.
    skill_root = tmp_path / "frontmatter-leak-skill"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text(
        "---\n"
        "name: frontmatter-leak-skill\n"
        "description: Uses SECRET_TOKEN from C:\\Users\\haemi\\private-profile.\n"
        "---\n"
        "Runtime steps are intentionally invalid for privacy validation.\n",
        encoding="utf-8",
    )

    # When: validating the custom root directly.
    result = _run_cli("skills", "validate", "--root", str(skill_root), "--json")

    # Then: the failure explains the error without echoing private frontmatter.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert "PRIVATE_DATA_FOUND" in payload["errors"]
    assert "SECRET_TOKEN" not in result.stdout
    assert "C:\\Users\\haemi" not in result.stdout


def test_skills_validate_redacts_custom_root_basename_from_id(tmp_path: Path) -> None:
    # Given: a valid custom root whose folder name itself contains private context.
    skill_root = tmp_path / "private-profile-skill-root-valid"
    skill_root.mkdir()
    (skill_root / "SKILL.md").write_text(
        "---\n"
        "name: valid-custom-skill\n"
        "description: Valid custom skill for validation.\n"
        "---\n"
        "Use this as a synthetic validation drawer.\n",
        encoding="utf-8",
    )

    # When: validating the custom root directly.
    result = _run_cli("skills", "validate", "--root", str(skill_root), "--json")

    # Then: public output uses a stable custom id, not the private folder basename.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["skills"][0]["id"] == "custom-skill"
    assert "private-profile" not in result.stdout


def test_skills_validate_redacts_custom_child_folder_from_path(tmp_path: Path) -> None:
    # Given: a custom skill drawer whose child folder name contains private context.
    skills_root = tmp_path / "custom-skills"
    skill_dir = skills_root / "private-profile-child-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: valid-child-skill\n"
        "description: Valid child skill for validation.\n"
        "---\n"
        "Use this as a synthetic child validation drawer.\n",
        encoding="utf-8",
    )

    # When: validating the custom root containing child skill directories.
    result = _run_cli("skills", "validate", "--root", str(skills_root), "--json")

    # Then: public output hides the private child folder basename as well.
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["skills"][0]["id"] == "custom-skill"
    assert payload["skills"][0]["path"] == "<custom-skill-root>/custom-skill/SKILL.md"
    assert "private-profile" not in result.stdout


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
    )
