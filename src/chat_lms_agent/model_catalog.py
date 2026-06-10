"""Three-tier model alias catalog: role -> family -> concrete.

Structural references: oh-my-pi ``packages/catalog`` identity layer and the
lazycodex role catalog. The catalog is data plus resolution only — the host
runtime owns execution. Every payload that names a model carries the
concrete id with the alias chain as provenance, never the alias alone.
The teacher's profile override re-points roles/families without touching
the repo default.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

CATALOG_SCHEMA_VERSION: Final = "model-catalog-v1"
RESOLUTION_SCHEMA_VERSION: Final = "model-resolution-v1"
PROFILE_CATALOG_FILE: Final = "model-catalog.json"
RESOLVE_COMMAND: Final = (
    "python -m chat_lms_agent harness model resolve --role <role> --json"
)


def resolve_role(
    repo_root: Path,
    role: str,
    profile: ProfileState | None = None,
) -> dict[str, JsonValue]:
    merged, sources = _merged_catalog(repo_root, profile)
    roles = _mapping(merged.get("roles"))
    role_entry = _mapping(roles.get(role))
    if not role_entry:
        known: list[JsonValue] = []
        known.extend(sorted(roles))
        return _error("UNKNOWN_ROLE", role=role, known=known)
    raw_family = role_entry.get("family")
    family = raw_family if isinstance(raw_family, str) else ""
    family_entry = _mapping(_mapping(merged.get("families")).get(family))
    if not family_entry:
        return _error("DANGLING_FAMILY", role=role, family=family)
    raw_concrete = family_entry.get("concrete")
    concrete = raw_concrete if isinstance(raw_concrete, str) else ""
    model_entry = _mapping(_mapping(merged.get("models")).get(concrete))
    if not model_entry:
        return _error("DANGLING_MODEL", role=role, family=family, concrete=concrete)
    if model_entry.get("status") == "deprecated":
        return _error("MODEL_DEPRECATED", role=role, family=family, concrete=concrete)
    provider = model_entry.get("provider")
    chain: list[JsonValue] = [role, family, concrete]
    payload: dict[str, JsonValue] = {
        "status": "PASS",
        "schema_version": RESOLUTION_SCHEMA_VERSION,
        "role": role,
        "family": family,
        "concrete": concrete,
        "provider": provider if isinstance(provider, str) else "unknown",
        "chain": chain,
        "source": sources.get(f"roles.{role}", "repo"),
        "catalog_version": merged.get("version"),
    }
    promotion = model_entry.get("context_promotion_target")
    if isinstance(promotion, str) and promotion:
        payload["context_promotion_target"] = promotion
    return payload


def validate_catalog(
    repo_root: Path,
    profile: ProfileState | None = None,
) -> dict[str, JsonValue]:
    merged, _ = _merged_catalog(repo_root, profile)
    roles = _mapping(merged.get("roles"))
    problems: list[JsonValue] = []
    for role in sorted(roles):
        result = resolve_role(repo_root, role, profile)
        if result["status"] != "PASS":
            problems.append(
                {
                    "role": role,
                    "error_code": result.get("error_code"),
                    "family": result.get("family"),
                    "concrete": result.get("concrete"),
                },
            )
    if problems:
        return {
            "status": "ERROR",
            "schema_version": CATALOG_SCHEMA_VERSION,
            "problems": problems,
        }
    return {
        "status": "PASS",
        "schema_version": CATALOG_SCHEMA_VERSION,
        "roles_checked": len(roles),
        "problems": [],
    }


def list_catalog(
    repo_root: Path,
    profile: ProfileState | None = None,
) -> dict[str, JsonValue]:
    merged, sources = _merged_catalog(repo_root, profile)
    roles = _mapping(merged.get("roles"))
    listed: dict[str, JsonValue] = {}
    for role in sorted(roles):
        result = resolve_role(repo_root, role, profile)
        listed[role] = {
            "concrete": result.get("concrete"),
            "family": result.get("family"),
            "status": result.get("status"),
            "source": sources.get(f"roles.{role}", "repo"),
        }
    return {
        "status": "PASS",
        "schema_version": CATALOG_SCHEMA_VERSION,
        "catalog_version": merged.get("version"),
        "roles": listed,
        "resolve_command": RESOLVE_COMMAND,
    }


def catalog_context(
    repo_root: Path,
    profile: ProfileState | None = None,
) -> dict[str, JsonValue]:
    """Compact staffing chart for hydration: role -> concrete id only."""
    merged, _ = _merged_catalog(repo_root, profile)
    roles = _mapping(merged.get("roles"))
    chart: dict[str, JsonValue] = {}
    for role in sorted(roles):
        result = resolve_role(repo_root, role, profile)
        if result["status"] == "PASS":
            chart[role] = result["concrete"]
    return {
        "schema_version": RESOLUTION_SCHEMA_VERSION,
        "roles": chart,
        "resolve_command": RESOLVE_COMMAND,
    }


def _merged_catalog(
    repo_root: Path,
    profile: ProfileState | None,
) -> tuple[dict[str, JsonValue], dict[str, str]]:
    base = _read_catalog(repo_root / "docs" / "model-catalog.json")
    sources: dict[str, str] = {}
    if profile is None:
        return base, sources
    override = _read_catalog(profile.root / STATE_DIR / PROFILE_CATALOG_FILE)
    if not override:
        return base, sources
    for section in ("roles", "families", "models"):
        base_section = dict(_mapping(base.get(section)))
        for key, value in _mapping(override.get(section)).items():
            base_section[key] = value
            sources[f"{section}.{key}"] = "profile"
        base[section] = cast("JsonValue", base_section)
    return base, sources


def _read_catalog(path: Path) -> dict[str, JsonValue]:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _mapping(value: JsonValue | None) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return value
    return {}


def _error(error_code: str, **fields: JsonValue) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "status": "ERROR",
        "schema_version": RESOLUTION_SCHEMA_VERSION,
        "error_code": error_code,
    }
    payload.update(fields)
    return payload
