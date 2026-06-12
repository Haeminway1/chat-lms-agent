from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

DesignSystemSource = Literal["repo", "profile"]

REPO_DESIGN_SYSTEMS_DIR: Final = "assets/design-systems"
PROFILE_DESIGN_SYSTEMS_DIR: Final = "design-systems"

_DESIGN_FILE: Final = "DESIGN.md"
_REQUIRED_SECTIONS: Final = (
    "identity",
    "color",
    "typography",
    "spacing",
    "components",
    "motion",
    "voice",
    "accessibility",
    "anti-patterns",
)


@dataclass(frozen=True, slots=True)
class DesignSystem:
    system_id: str
    source: DesignSystemSource
    name: str
    summary: str
    design_path: Path


def load_design_systems(
    repo_root: Path,
    profile: ProfileState | None = None,
) -> tuple[list[DesignSystem], list[str]]:
    systems: dict[str, DesignSystem] = {}
    warnings: list[str] = []
    _load_dir(repo_root / REPO_DESIGN_SYSTEMS_DIR, "repo", systems, warnings)
    if profile is not None:
        _load_dir(
            profile.root / STATE_DIR / PROFILE_DESIGN_SYSTEMS_DIR,
            "profile",
            systems,
            warnings,
        )
    return [systems[system_id] for system_id in sorted(systems)], warnings


def design_systems_list_json(
    repo_root: Path,
    profile: ProfileState | None = None,
) -> dict[str, JsonValue]:
    systems, warnings = load_design_systems(repo_root, profile)
    entries: list[JsonValue] = [
        {"id": system.system_id, "source": system.source, "summary": system.summary}
        for system in systems
    ]
    return {"status": "PASS", "systems": entries, "warnings": [*warnings]}


def _load_dir(
    directory: Path,
    source: DesignSystemSource,
    systems: dict[str, DesignSystem],
    warnings: list[str],
) -> None:
    if not directory.is_dir():
        return
    for design_path in sorted(directory.glob(f"*/{_DESIGN_FILE}")):
        system, warning = _parse_design_system(design_path, directory, source)
        if warning is not None:
            warnings.append(warning)
            continue
        if system is not None:
            systems[system.system_id] = system


def _parse_design_system(
    design_path: Path,
    root: Path,
    source: DesignSystemSource,
) -> tuple[DesignSystem | None, str | None]:
    try:
        text = design_path.read_text(encoding="utf-8-sig")
    except OSError:
        return None, f"{_warning_path(root, design_path)}: DESIGN_READ_ERROR"
    error = _schema_error(text)
    if error is not None:
        return None, f"{_warning_path(root, design_path)}: {error}"
    return (
        DesignSystem(
            system_id=design_path.parent.name,
            source=source,
            name=_title(text),
            summary=_summary(text),
            design_path=design_path,
        ),
        None,
    )


def _schema_error(text: str) -> str | None:
    sections = set(_section_names(text))
    if not all(section in sections for section in _REQUIRED_SECTIONS):
        return "INVALID_DESIGN_SCHEMA"
    if not _summary(text):
        return "INVALID_DESIGN_SCHEMA"
    return None


def _section_names(text: str) -> tuple[str, ...]:
    names: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("## "):
            continue
        names.append(stripped.removeprefix("## ").strip().lower())
    return tuple(names)


def _title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
    return "Untitled design system"


def _summary(text: str) -> str:
    in_identity = False
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered == "## identity":
            in_identity = True
            continue
        if in_identity and stripped.startswith("## "):
            return ""
        if not in_identity:
            continue
        if lowered.startswith("summary:"):
            return stripped.split(":", maxsplit=1)[1].strip()
    return ""


def _warning_path(root: Path, design_path: Path) -> str:
    try:
        return design_path.relative_to(root).as_posix()
    except ValueError:
        return design_path.name
