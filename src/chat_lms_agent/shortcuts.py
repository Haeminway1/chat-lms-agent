from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast

from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

SHORTCUT_SCHEMA_VERSION: Final = "shortcut-v1"
SHORTCUTS_DIR: Final = "shortcuts"


@dataclass(frozen=True, slots=True)
class Shortcut:
    name: str
    run: str
    description: str
    open_browser: bool
    source: str = "profile"


@dataclass(frozen=True, slots=True)
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def __call__(self, command: str) -> CommandResult:
        """Run a shortcut command string and return captured output."""
        ...


class BrowserOpener(Protocol):
    def __call__(self, url: str) -> bool:
        """Open a URL produced by a shortcut command."""
        ...


def load_shortcuts(profile: ProfileState) -> tuple[list[Shortcut], list[str]]:
    shortcuts: dict[str, Shortcut] = {}
    warnings: list[str] = []
    directory = _shortcuts_dir(profile)
    if not directory.is_dir():
        return [], []
    for path in sorted(directory.glob("*.json")):
        shortcut, warning = _parse_shortcut(path)
        if warning is not None:
            warnings.append(warning)
            continue
        if shortcut is not None:
            shortcuts[shortcut.name] = shortcut
    return [shortcuts[name] for name in sorted(shortcuts)], warnings


def save_shortcut(profile: ProfileState, shortcut: Shortcut) -> Path:
    path = _shortcut_path(profile, shortcut.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, JsonValue] = {
        "schema_version": SHORTCUT_SCHEMA_VERSION,
        "name": shortcut.name,
        "run": shortcut.run,
        "open_browser": shortcut.open_browser,
    }
    if shortcut.description:
        payload["description"] = shortcut.description
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    _ = tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)
    return path


def remove_shortcut(profile: ProfileState, name: str) -> bool:
    if not _safe_file_stem(name):
        return False
    path = _shortcut_path(profile, name)
    if not path.exists():
        return False
    path.unlink()
    return True


def shortcut_to_json(shortcut: Shortcut) -> dict[str, JsonValue]:
    return {
        "schema_version": SHORTCUT_SCHEMA_VERSION,
        "name": shortcut.name,
        "description": shortcut.description,
        "run": shortcut.run,
        "open_browser": shortcut.open_browser,
    }


def shortcut_list_item(shortcut: Shortcut) -> dict[str, JsonValue]:
    return {
        "name": shortcut.name,
        "description": shortcut.description,
        "source": shortcut.source,
    }


def validate_shortcut_fields(name: str, run: str) -> list[str]:
    errors: list[str] = []
    if not name.strip():
        errors.append("EMPTY_NAME")
    if not run.strip():
        errors.append("EMPTY_RUN")
    if name.strip() and not _safe_file_stem(name.strip()):
        errors.append("INVALID_NAME")
    return errors


def last_non_empty_stdout_line(stdout: str) -> str:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1]


def find_shortcut(profile: ProfileState, name: str) -> Shortcut | None:
    shortcuts, _warnings = load_shortcuts(profile)
    for shortcut in shortcuts:
        if shortcut.name == name:
            return shortcut
    return None


def _shortcuts_dir(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / SHORTCUTS_DIR


def _shortcut_path(profile: ProfileState, name: str) -> Path:
    return _shortcuts_dir(profile) / f"{name}.json"


def _parse_shortcut(path: Path) -> tuple[Shortcut | None, str | None]:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return None, f"{path.name}: INVALID_JSON"
    if not isinstance(payload, dict):
        return None, f"{path.name}: NOT_AN_OBJECT"
    error = _shortcut_error(payload)
    if error is not None:
        return None, f"{path.name}: {error}"
    return (
        Shortcut(
            name=_string(payload.get("name")).strip(),
            run=_string(payload.get("run")).strip(),
            description=_string(payload.get("description")),
            open_browser=payload.get("open_browser") is True,
        ),
        None,
    )


def _shortcut_error(payload: dict[str, JsonValue]) -> str | None:
    errors: list[str] = []
    if payload.get("schema_version") != SHORTCUT_SCHEMA_VERSION:
        errors.append("UNSUPPORTED_SCHEMA_VERSION")
    name = payload.get("name")
    run = payload.get("run")
    description = payload.get("description")
    open_browser = payload.get("open_browser")
    if not isinstance(name, str) or not name.strip():
        errors.append("EMPTY_NAME")
    elif not _safe_file_stem(name.strip()):
        errors.append("INVALID_NAME")
    if not isinstance(run, str) or not run.strip():
        errors.append("EMPTY_RUN")
    if description is not None and not isinstance(description, str):
        errors.append("INVALID_DESCRIPTION")
    if open_browser is not None and not isinstance(open_browser, bool):
        errors.append("INVALID_OPEN_BROWSER")
    return errors[0] if errors else None


def _string(value: JsonValue | None) -> str:
    if isinstance(value, str):
        return value
    return ""


def _safe_file_stem(name: str) -> bool:
    return Path(name).name == name and name not in {".", ".."}
