from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, cast

from chat_lms_agent.cli_io import (
    option,
    profile_state_or_error,
    required_option,
    subcommand,
    write_json,
)
from chat_lms_agent.journal import redact_runtime_text
from chat_lms_agent.memory_levels import memory_levels_payload
from chat_lms_agent.memory_obligations import (
    obligation_to_draft_json,
    obligations_from_inputs,
)
from chat_lms_agent.state import (
    STATE_DIR,
    JsonValue,
    MemoryPayload,
    ProfileState,
    load_memory,
    redact_text,
    save_memory,
)

if TYPE_CHECKING:
    from collections.abc import Callable


def handle_memory(args: list[str], repo_root: Path) -> int:
    if subcommand(args) == "levels":
        write_json(memory_levels_payload())
        return 0
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    command = subcommand(args)
    handlers: dict[str, Callable[[], int]] = {
        "list": lambda: _list(profile),
        "upsert": lambda: _upsert(args, profile),
        "compact": lambda: _compact(profile),
        "archive": lambda: _archive(args, profile),
        "verify": lambda: _verify(args, profile),
        "draft": lambda: _draft(args),
        "apply-draft": lambda: _apply_draft(args, profile),
    }
    handler = handlers.get(command)
    if handler is None:
        write_json({"status": "ERROR", "error_code": "UNKNOWN_MEMORY_COMMAND"})
        return 2
    return handler()


def _list(profile: ProfileState) -> int:
    entries = load_memory(profile)
    write_json({"status": "PASS", "memory": [_memory_json(entry) for entry in entries]})
    return 0


def _upsert(args: list[str], profile: ProfileState) -> int:
    entry: MemoryPayload = {
        "key": required_option(args, "--key"),
        "scope": required_option(args, "--scope"),
        "text": redact_runtime_text(profile, required_option(args, "--text")),
    }
    entries = load_memory(profile)
    next_entries = [item for item in entries if item["key"] != entry["key"]]
    next_entries.append(entry)
    save_memory(profile, sorted(next_entries, key=lambda item: item["key"]))
    write_json({"status": "PASS", "memory": _memory_json(entry)})
    return 0


def _compact(profile: ProfileState) -> int:
    entries = load_memory(profile)
    compacted_keys = [entry["key"] for entry in entries]
    compacted_values: list[JsonValue] = []
    compacted_values.extend(compacted_keys)
    scope_values: list[JsonValue] = []
    scope_values.extend(sorted({entry["scope"] for entry in entries}))
    summary: dict[str, JsonValue] = {
        "hydrated_by_default": True,
        "entry_count": len(entries),
        "scopes": scope_values,
    }
    payload: dict[str, JsonValue] = {
        "status": "PASS",
        "schema_version": "memory-compact-v1",
        "profile_root": "<profile-root>",
        "compacted_keys": compacted_values,
        "summary": summary,
    }
    _write_state_json(profile.root / STATE_DIR / "memory-compact.json", payload)
    write_json(payload)
    return 0


def _archive(args: list[str], profile: ProfileState) -> int:
    key = required_option(args, "--key")
    entries = load_memory(profile)
    active = [entry for entry in entries if entry["key"] != key]
    archived = next((entry for entry in entries if entry["key"] == key), None)
    if archived is None:
        write_json({"status": "ERROR", "error_code": "MEMORY_KEY_NOT_FOUND"})
        return 2
    save_memory(profile, active)
    archive_payload = _read_state_json(profile.root / STATE_DIR / "memory-archive.json")
    archived_entries = archive_payload.get("archived")
    if not isinstance(archived_entries, list):
        archived_entries = []
    archived_record: dict[str, JsonValue] = {
        "key": archived["key"],
        "scope": archived["scope"],
        "text": archived["text"],
        "hydrated_by_default": False,
    }
    archived_entries.append(archived_record)
    _write_state_json(
        profile.root / STATE_DIR / "memory-archive.json",
        {"archived": archived_entries},
    )
    write_json(
        {
            "status": "PASS",
            "archived": {
                "key": archived["key"],
                "scope": archived["scope"],
                "hydrated_by_default": False,
            },
        },
    )
    return 0


def _verify(args: list[str], profile: ProfileState) -> int:
    obligations = obligations_from_inputs(option(args, "--changed-files"), option(args, "--for"))
    memory_keys = {entry["key"] for entry in load_memory(profile)}
    missing = [item for item in obligations if item.key not in memory_keys]
    if not missing:
        write_json({"status": "PASS", "missing_memory": []})
        return 0
    write_json(
        {
            "status": "BLOCKED",
            "error_code": "MEMORY_UPDATE_REQUIRED",
            "missing_memory": [item.key for item in missing],
            "drafts": [obligation_to_draft_json(item) for item in missing],
        },
    )
    return 5


def _draft(args: list[str]) -> int:
    obligations = obligations_from_inputs(option(args, "--changed-files"), option(args, "--for"))
    drafts: list[JsonValue] = [obligation_to_draft_json(item) for item in obligations]
    payload: dict[str, JsonValue] = {"status": "PASS", "memory": drafts}
    out_path = option(args, "--out")
    if out_path is not None:
        _write_draft(Path(out_path), payload)
        payload["draft_path"] = "<draft-path>"
    write_json(payload)
    return 0


def _apply_draft(args: list[str], profile: ProfileState) -> int:
    raw = _read_draft(Path(required_option(args, "--from")))
    if raw is None:
        write_json({"status": "ERROR", "error_code": "INVALID_MEMORY_DRAFT"})
        return 2
    entries = load_memory(profile)
    incoming = _draft_entries(raw)
    if not incoming:
        write_json({"status": "ERROR", "error_code": "INVALID_MEMORY_DRAFT"})
        return 2
    incoming_keys = {entry["key"] for entry in incoming}
    next_entries = [item for item in entries if item["key"] not in incoming_keys]
    next_entries.extend(incoming)
    save_memory(profile, sorted(next_entries, key=lambda item: item["key"]))
    write_json({"status": "PASS", "applied": [entry["key"] for entry in incoming]})
    return 0


def _write_draft(path: Path, payload: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_draft(path: Path) -> dict[str, JsonValue] | None:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _read_state_json(path: Path) -> dict[str, JsonValue]:
    if not path.exists():
        return {}
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8")))
    except (JSONDecodeError, OSError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _write_state_json(path: Path, payload: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    _ = tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)


def _draft_entries(payload: dict[str, JsonValue]) -> list[MemoryPayload]:
    raw_entries = payload.get("memory", [])
    if not isinstance(raw_entries, list):
        return []
    entries: list[MemoryPayload] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        scope = item.get("scope")
        text = item.get("text")
        if isinstance(key, str) and isinstance(scope, str) and isinstance(text, str):
            entries.append({"key": key, "scope": scope, "text": redact_text(text)})
    return entries


def _memory_json(entry: MemoryPayload) -> dict[str, JsonValue]:
    return {
        "key": entry["key"],
        "scope": entry["scope"],
        "text": entry["text"],
    }
