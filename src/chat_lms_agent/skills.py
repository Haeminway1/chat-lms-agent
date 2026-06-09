from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

PRIVATE_PATTERNS: Final = (
    re.compile(r"\b[A-Z][A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD)[A-Z0-9_]*\b"),
    re.compile(r"(?i)\b(?:secret|token|password)\s*[=:]\s*[^\s,;]+"),
    re.compile(r"(?i)\blearner record:"),
    re.compile(r"(?:[A-Za-z]:[\\/]|/(?:Users|home|tmp|var/tmp|private/tmp|var/folders)/)"),
)
MAX_SKILL_CHARS: Final = 12_000
MIN_FRONTMATTER_PARTS: Final = 3


@dataclass(frozen=True, slots=True)
class SkillRecord:
    skill_id: str
    name: str
    description: str
    trigger_summary: str
    path: str
    errors: tuple[str, ...]


def skills_payload(repo_root: Path, root_override: Path | None = None) -> dict[str, JsonValue]:
    records = _skill_records(repo_root, root_override)
    return {
        "status": "PASS",
        "schema_version": "skills-v1",
        "skills": [_record_json(record) for record in records],
    }


def skills_validation_payload(
    repo_root: Path,
    root_override: Path | None = None,
) -> tuple[int, dict[str, JsonValue]]:
    records = _skill_records(repo_root, root_override)
    errors = [error for record in records for error in record.errors]
    private_data_found = any("PRIVATE_DATA_FOUND" in record.errors for record in records)
    skill_values: list[JsonValue] = [_record_json(record) for record in records]
    error_values: list[JsonValue] = list(errors)
    payload: dict[str, JsonValue] = {
        "status": "PASS" if not errors else "ERROR",
        "schema_version": "skills-v1",
        "skills": skill_values,
        "private_data_found": private_data_found,
        "errors": error_values,
    }
    return (0 if not errors else 2), payload


def _skill_records(repo_root: Path, root_override: Path | None) -> list[SkillRecord]:
    skills_root = _skills_root(repo_root, root_override)
    if not skills_root.exists():
        return []
    use_custom_ids = root_override is not None
    skill_md = skills_root / "SKILL.md"
    if skill_md.exists():
        skill_id = "custom-skill" if use_custom_ids else skills_root.name
        return [
            _read_skill(
                skills_root,
                repo_root,
                skills_root,
                skill_id,
                custom_root=use_custom_ids,
            ),
        ]
    skill_dirs = sorted(path for path in skills_root.iterdir() if path.is_dir())
    return [
        _read_skill(
            skill_dir,
            repo_root,
            skills_root,
            _custom_skill_id(index) if use_custom_ids else skill_dir.name,
            custom_root=use_custom_ids,
        )
        for index, skill_dir in enumerate(skill_dirs, start=1)
    ]


def _read_skill(
    skill_dir: Path,
    repo_root: Path,
    skills_root: Path,
    skill_id: str,
    *,
    custom_root: bool,
) -> SkillRecord:
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.exists():
        return SkillRecord(
            skill_id,
            "",
            "",
            "",
            _public_path(
                skill_path,
                repo_root,
                skills_root,
                skill_id,
                custom_root=custom_root,
            ),
            ("MISSING_SKILL_MD",),
        )
    content = skill_path.read_text(encoding="utf-8")
    frontmatter = _frontmatter(content)
    errors: list[str] = []
    if frontmatter is None:
        errors.append("MISSING_SKILL_FRONTMATTER")
        frontmatter = {}
    name = _redact_public_text(frontmatter.get("name", ""))
    description = _redact_public_text(frontmatter.get("description", ""))
    trigger_summary = _trigger_summary(description)
    if not name:
        errors.append("MISSING_SKILL_NAME")
    if not description:
        errors.append("MISSING_SKILL_DESCRIPTION")
    if len(content) > MAX_SKILL_CHARS:
        errors.append("SKILL_TOO_LARGE")
    if _has_private_data(content):
        errors.append("PRIVATE_DATA_FOUND")
    return SkillRecord(
        skill_id=skill_id,
        name=name,
        description=description,
        trigger_summary=trigger_summary,
        path=_public_path(
            skill_path,
            repo_root,
            skills_root,
            skill_id,
            custom_root=custom_root,
        ),
        errors=tuple(errors),
    )


def _frontmatter(content: str) -> dict[str, str] | None:
    if not content.startswith("---\n"):
        return None
    parts = content.split("---", maxsplit=2)
    if len(parts) < MIN_FRONTMATTER_PARTS:
        return None
    values: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        values[key.strip()] = value.strip().strip('"')
    return values


def _record_json(record: SkillRecord) -> dict[str, JsonValue]:
    return {
        "id": record.skill_id,
        "name": record.name,
        "description": record.description,
        "trigger_summary": record.trigger_summary,
        "path": record.path,
        "errors": list(record.errors),
    }


def _skills_root(repo_root: Path, root_override: Path | None) -> Path:
    if root_override is None:
        return repo_root / ".agents" / "skills"
    return root_override


def _custom_skill_id(index: int) -> str:
    if index == 1:
        return "custom-skill"
    return f"custom-skill-{index}"


def _trigger_summary(description: str) -> str:
    summary = description.strip()
    if not summary:
        return ""
    sentence, *_ = summary.split(".", maxsplit=1)
    return sentence.strip() or summary


def _has_private_data(content: str) -> bool:
    return any(pattern.search(content) is not None for pattern in PRIVATE_PATTERNS)


def _redact_public_text(value: str) -> str:
    redacted = re.sub(
        r"\b[A-Z][A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD)[A-Z0-9_]*(?:=[^\s,;]+)?\b",
        "[redacted]",
        value,
    )
    redacted = re.sub(
        r"(?i)\b(?:secret|token|password)\s*[=:]\s*[^\s,;]+",
        "[redacted]",
        redacted,
    )
    return re.sub(
        r"(?:[A-Za-z]:[\\/]|/(?:Users|home|tmp|var/tmp|private/tmp|var/folders)/)[^\s,;]+",
        "<local-path>",
        redacted,
    )


def _public_path(
    path: Path,
    repo_root: Path,
    skills_root: Path,
    skill_id: str,
    *,
    custom_root: bool,
) -> str:
    if custom_root:
        root_relative = _relative_path(path, skills_root)
        if root_relative == "SKILL.md":
            return "<custom-skill-root>/SKILL.md"
        return f"<custom-skill-root>/{skill_id}/SKILL.md"
    repo_relative = _relative_path(path, repo_root)
    if repo_relative is not None:
        return repo_relative
    root_relative = _relative_path(path, skills_root)
    if root_relative is None:
        return f"<custom-skill-root>/{path.name}"
    return f"<custom-skill-root>/{root_relative}"


def _relative_path(path: Path, root: Path) -> str | None:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None
