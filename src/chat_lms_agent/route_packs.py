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
            token.lower() in lowered for token in pack.any_tokens
        )
        if required_match and any_match:
            return pack
    return None


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


def route_packs_context(packs: list[RoutePack]) -> dict[str, JsonValue]:
    cards: list[JsonValue] = [
        pack_route_context(pack) for pack in packs if pack.bucket == "always_inject"
    ]
    listed: list[JsonValue] = [
        {
            "route_id": pack.pack_id,
            "bucket": pack.bucket,
            "summary": pack.summary,
            "source": pack.source,
        }
        for pack in packs
        if pack.bucket != "always_inject"
    ]
    return {
        "schema_version": ROUTE_PACK_SCHEMA_VERSION,
        "cards": cards,
        "listed": listed,
    }


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
