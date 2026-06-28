"""Data-driven prompt route packs: routes are data, not code.

Structural reference: the oh-my-pi rulebook pipeline — one normalized shape
from many files, name-keyed first-wins precedence (profile over repo), three
buckets (always_inject / listed_lazy / trigger), and tolerant per-file
failure: one malformed pack warns and is skipped, never aborting discovery.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, Literal, cast

from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

ROUTE_PACK_SCHEMA_VERSION: Final = "route-pack-v1"
ROUTE_PACK_SCHEMA_VERSION_V2: Final = "route-pack-v2"
REPO_ROUTES_DIR: Final = "routes"
PROFILE_ROUTES_DIR: Final = "routes"
DEFAULT_COMMAND_INDEX_BUDGET: Final = 2_800
COMMAND_INDEX_RECOVERY_HINT: Final = "python -m chat_lms_agent agent-tools route list --json"
COMMAND_INDEX_TRUNCATED_MARKER: Final = "COMMAND_INDEX_TRUNCATED"

type PackBucket = Literal["always_inject", "listed_lazy", "trigger"]
type PackSource = Literal["repo", "profile"]

_BUCKETS: Final = frozenset({"always_inject", "listed_lazy", "trigger"})
_SUPPORTED_SCHEMA_VERSIONS: Final = frozenset(
    {ROUTE_PACK_SCHEMA_VERSION, ROUTE_PACK_SCHEMA_VERSION_V2},
)


@dataclass(frozen=True, slots=True)
class RoutePack:
    pack_id: str
    schema_version: str
    bucket: PackBucket
    summary: str
    required_tokens: tuple[str, ...]
    any_tokens: tuple[str, ...]
    first_command: str
    then_command: str
    fallback_command: str
    must_not: tuple[str, ...]
    time_budget_ms: int
    source: PackSource


def load_route_packs(
    repo_root: Path,
    profile: ProfileState | None = None,
) -> tuple[list[RoutePack], list[str]]:
    """Load repo defaults then profile additions; profile wins by pack id."""
    packs: dict[str, RoutePack] = {}
    warnings: list[str] = []
    _load_dir(repo_root / REPO_ROUTES_DIR, "repo", packs, warnings)
    if profile is not None:
        _load_dir(profile.root / STATE_DIR / PROFILE_ROUTES_DIR, "profile", packs, warnings)
    return [packs[pack_id] for pack_id in sorted(packs)], warnings


def match_pack_route(packs: list[RoutePack], prompt: str) -> RoutePack | None:
    lowered = prompt.lower()
    for pack in packs:
        if pack.bucket != "trigger":
            continue
        required_match = all(token.lower() in lowered for token in pack.required_tokens)
        any_match = not pack.any_tokens or any(
            _matches_prompt_token(lowered, token.lower()) for token in pack.any_tokens
        )
        if required_match and any_match:
            return pack
    return None


def _matches_prompt_token(prompt: str, token: str) -> bool:
    if not _has_whitespace(token):
        return token in prompt
    start = 0
    while True:
        index = prompt.find(token, start)
        if index == -1:
            return False
        end = index + len(token)
        if _has_text_boundary(prompt, index - 1) and _has_text_boundary(prompt, end):
            return True
        start = index + 1


def _has_whitespace(value: str) -> bool:
    return any(char.isspace() for char in value)


def _has_text_boundary(text: str, index: int) -> bool:
    if index < 0 or index >= len(text):
        return True
    return not text[index].isalnum()


def pack_route_context(pack: RoutePack) -> dict[str, JsonValue]:
    must_not: list[JsonValue] = []
    must_not.extend(pack.must_not)
    return {
        "schema_version": pack.schema_version,
        "route_id": pack.pack_id,
        "source": pack.source,
        "summary": pack.summary,
        "first_command": pack.first_command,
        "then_command": pack.then_command,
        "fallback_command": pack.fallback_command,
        "must_not": must_not,
        "time_budget_ms": pack.time_budget_ms,
    }


def route_packs_context(
    packs: list[RoutePack],
    *,
    command_index_budget: int = DEFAULT_COMMAND_INDEX_BUDGET,
) -> dict[str, JsonValue]:
    cards: list[JsonValue] = [
        pack_route_context(pack) for pack in packs if pack.bucket == "always_inject"
    ]
    command_index, dropped_route_ids = _command_index(packs, command_index_budget)
    listed: list[JsonValue] = [
        _listed_item(
            pack,
            command_index_dropped=pack.pack_id in dropped_route_ids,
        )
        for pack in packs
        if pack.bucket != "always_inject"
    ]
    return {
        "schema_version": ROUTE_PACK_SCHEMA_VERSION,
        "cards": cards,
        "listed": listed,
        "command_index": command_index,
    }


def _listed_item(pack: RoutePack, *, command_index_dropped: bool) -> dict[str, JsonValue]:
    item: dict[str, JsonValue] = {
            "route_id": pack.pack_id,
            "bucket": pack.bucket,
            "summary": pack.summary,
            "source": pack.source,
        }
    if command_index_dropped:
        item["command_index_dropped"] = True
        item["recovery_hint"] = COMMAND_INDEX_RECOVERY_HINT
    return item


def _command_index(
    packs: list[RoutePack],
    budget: int,
) -> tuple[list[JsonValue], set[str]]:
    entries: list[dict[str, JsonValue]] = [
        _command_index_entry(pack) for pack in sorted(packs, key=_command_index_sort_key)
        if pack.bucket in {"always_inject", "trigger"} and pack.first_command
    ]
    dropped: set[str] = set()
    kept: list[dict[str, JsonValue]] = []
    for entry in entries:
        candidate = [*kept, entry]
        if _fits_command_index_budget(candidate, budget):
            kept.append(entry)
            continue
        compact = _compact_command_index_entry(entry)
        if compact is not entry and _fits_command_index_budget([*kept, compact], budget):
            kept.append(compact)
            continue
        if _must_not_is_non_droppable(entry) and _append_after_droppable_eviction(
            kept,
            entry,
            dropped,
            budget,
        ):
            continue
        route_id = entry.get("route_id")
        if isinstance(route_id, str):
            dropped.add(route_id)
    if dropped and _fits_command_index_budget(
        [*kept, _command_index_truncation_marker(dropped)],
        budget,
    ):
        kept.append(_command_index_truncation_marker(dropped))
    items: list[JsonValue] = []
    items.extend(kept)
    return items, dropped


def _append_after_droppable_eviction(
    kept: list[dict[str, JsonValue]],
    required_entry: dict[str, JsonValue],
    dropped: set[str],
    budget: int,
) -> bool:
    while not _fits_command_index_budget([*kept, required_entry], budget):
        drop_index = _last_droppable_index(kept)
        if drop_index is None:
            return False
        dropped_entry = kept.pop(drop_index)
        route_id = dropped_entry.get("route_id")
        if isinstance(route_id, str):
            dropped.add(route_id)
    kept.append(required_entry)
    return True


def _last_droppable_index(entries: list[dict[str, JsonValue]]) -> int | None:
    for index in range(len(entries) - 1, -1, -1):
        if not _must_not_is_non_droppable(entries[index]):
            return index
    return None


def _command_index_sort_key(pack: RoutePack) -> tuple[int, str]:
    return (0 if pack.source == "profile" else 1, pack.pack_id)


def _command_index_entry(pack: RoutePack) -> dict[str, JsonValue]:
    must_not: list[JsonValue] = []
    must_not.extend(pack.must_not)
    return {
        "route_id": pack.pack_id,
        "summary": pack.summary,
        "first_command": pack.first_command,
        "then_command": pack.then_command,
        "must_not": must_not,
        "source": pack.source,
    }


def _compact_command_index_entry(entry: dict[str, JsonValue]) -> dict[str, JsonValue]:
    if _must_not_is_non_droppable(entry):
        return entry
    compacted = dict(entry)
    compacted["must_not"] = []
    return compacted


def _must_not_is_non_droppable(entry: dict[str, JsonValue]) -> bool:
    route_id = entry.get("route_id")
    first_command = entry.get("first_command")
    then_command = entry.get("then_command")
    first_text = first_command if isinstance(first_command, str) else ""
    then_text = then_command if isinstance(then_command, str) else ""
    command_text = f"{first_text} {then_text}"
    return (
        route_id in {"record_class", "record_test_scores"}
        or "write-action apply" in command_text
    )


def _command_index_truncation_marker(dropped: set[str]) -> dict[str, JsonValue]:
    return {
        "truncated": True,
        "marker": COMMAND_INDEX_TRUNCATED_MARKER,
        "omitted": len(dropped),
        "recovery_hint": COMMAND_INDEX_RECOVERY_HINT,
    }


def _fits_command_index_budget(entries: list[dict[str, JsonValue]], budget: int) -> bool:
    return _json_size(entries) <= budget


def _json_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def _load_dir(
    directory: Path,
    source: PackSource,
    packs: dict[str, RoutePack],
    warnings: list[str],
) -> None:
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.json")):
        pack, warning = _parse_pack(path, source)
        if warning is not None:
            warnings.append(warning)
            continue
        if pack is not None:
            packs[pack.pack_id] = pack


def _parse_pack(path: Path, source: PackSource) -> tuple[RoutePack | None, str | None]:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return None, f"{path.name}: INVALID_JSON"
    if not isinstance(payload, dict):
        return None, f"{path.name}: NOT_AN_OBJECT"
    error = _pack_error(payload)
    if error is not None:
        return None, f"{path.name}: {error}"
    pack_id = payload.get("id")
    bucket = payload.get("bucket")
    time_budget = payload.get("time_budget_ms")
    schema_version = _schema_version(payload)
    if schema_version is None:
        schema_version = ROUTE_PACK_SCHEMA_VERSION
    any_tokens = (
        _string_tuple(payload.get("any_tokens"))
        if schema_version == ROUTE_PACK_SCHEMA_VERSION_V2
        else ()
    )
    return (
        RoutePack(
            pack_id=pack_id if isinstance(pack_id, str) else "",
            schema_version=schema_version,
            bucket=cast("PackBucket", bucket),
            summary=_string(payload.get("summary")),
            required_tokens=_string_tuple(payload.get("required_tokens")),
            any_tokens=any_tokens,
            first_command=_string(payload.get("first_command")),
            then_command=_string(payload.get("then_command")),
            fallback_command=_string(payload.get("fallback_command")),
            must_not=_string_tuple(payload.get("must_not")),
            time_budget_ms=(
                time_budget
                if isinstance(time_budget, int) and not isinstance(time_budget, bool)
                else 5000
            ),
            source=source,
        ),
        None,
    )


def _pack_error(payload: dict[str, JsonValue]) -> str | None:
    schema_version = _schema_version(payload)
    if schema_version is None:
        return "UNSUPPORTED_SCHEMA_VERSION"
    pack_id = payload.get("id")
    if not isinstance(pack_id, str) or not pack_id.strip():
        return "MISSING_ID"
    bucket = payload.get("bucket")
    if not isinstance(bucket, str) or bucket not in _BUCKETS:
        return "INVALID_BUCKET"
    required_tokens = _string_tuple(payload.get("required_tokens"))
    any_tokens = (
        _string_tuple(payload.get("any_tokens"))
        if schema_version == ROUTE_PACK_SCHEMA_VERSION_V2
        else ()
    )
    if bucket == "trigger" and not required_tokens and not any_tokens:
        return "TRIGGER_REQUIRES_TOKENS"
    if bucket != "listed_lazy" and not _string(payload.get("first_command")):
        return "MISSING_FIRST_COMMAND"
    return None


def _schema_version(payload: dict[str, JsonValue]) -> str | None:
    raw = payload.get("schema_version")
    if isinstance(raw, str) and raw in _SUPPORTED_SCHEMA_VERSIONS:
        return raw
    return None


def _string(value: JsonValue | None) -> str:
    if isinstance(value, str):
        return value
    return ""


def _string_tuple(value: JsonValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())
