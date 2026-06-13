from __future__ import annotations

import json
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

if TYPE_CHECKING:
    from pathlib import Path

from chat_lms_agent.academy_db import (
    ACADEMY_STATE_DIR,
    V3_SCHEMA_VERSION,
    create_backup,
    store_path,
)
from chat_lms_agent.academy_db_import_normalization import (
    import_plan_payload,
    normalize_import_payload,
    store_counts,
)
from chat_lms_agent.approvals import (
    approval_id_for,
    approval_is_approved,
    approval_is_consumed,
    approval_is_denied,
    consume_approval,
    ensure_approval_request,
)
from chat_lms_agent.journal import write_audit, write_trace
from chat_lms_agent.state import STATE_DIR, JsonValue, ProfileState

IMPORTS_DIR: Final = "imports"
IMPORT_PLANS_FILE: Final = "import-plans.json"
IMPORT_PLAN_ID: Final = "import_plan_latest"


def plan_import(profile: ProfileState, source_path: Path, repo_root: Path) -> dict[str, JsonValue]:
    source = _read_import_source(source_path, repo_root)
    if source["status"] != "PASS":
        return source
    payload = source.get("payload")
    if not isinstance(payload, dict):
        return {"status": "ERROR", "error_code": "INVALID_ACADEMY_IMPORT_SOURCE"}
    plan = import_plan_payload(payload, source, IMPORT_PLAN_ID, approval_id_for(IMPORT_PLAN_ID))
    _persist_import_plan(profile, plan)
    return plan


def apply_import(
    profile: ProfileState,
    source_path: Path,
    repo_root: Path,
    approval_id: str | None,
) -> dict[str, JsonValue]:
    source = _read_import_source(source_path, repo_root)
    if source["status"] != "PASS":
        return source
    payload = source.get("payload")
    if not isinstance(payload, dict):
        return {"status": "ERROR", "error_code": "INVALID_ACADEMY_IMPORT_SOURCE"}
    plan = import_plan_payload(payload, source, IMPORT_PLAN_ID, approval_id_for(IMPORT_PLAN_ID))
    plan_id = _string_value(plan.get("plan_id"), IMPORT_PLAN_ID)
    plan_approval_id = approval_id_for(plan_id)
    if approval_is_denied(profile, plan_approval_id, plan_id):
        return {
            "status": "ERROR",
            "error_code": "APPROVAL_DENIED",
            "approval_id": approval_id if approval_id is not None else plan_approval_id,
        }
    if approval_is_consumed(profile, plan_approval_id, plan_id):
        return {
            "status": "ERROR",
            "error_code": "APPROVAL_CONSUMED",
            "approval_id": approval_id if approval_id is not None else plan_approval_id,
        }
    _persist_import_plan(profile, plan)
    if approval_id is None or not approval_is_approved(profile, approval_id, plan_id):
        request = ensure_approval_request(
            profile,
            plan_id=plan_id,
            operation="academy-db.import.apply",
        )
        _ = write_trace(
            profile,
            "academy_db_import_needs_approval",
            "Academy DB import apply paused for human approval.",
            {"plan_id": plan_id},
        )
        _ = write_audit(
            profile,
            "academy-db.import.apply",
            "Academy DB import apply requested approval before writing.",
            {"plan_id": plan_id},
        )
        return request
    _ = create_backup(profile)
    normalized_payload = normalize_import_payload(payload)[0]
    _merge_import_payload(profile, normalized_payload)
    _mark_import_plan_applied(profile, plan_id)
    consume_approval(profile, approval_id, plan_id)
    _ = write_trace(
        profile,
        "academy_db_import_applied",
        "Academy DB import applied after human approval.",
        {
            "plan_id": plan_id,
            "approval_id": approval_id,
            "counts": store_counts(normalized_payload),
        },
    )
    _ = write_audit(
        profile,
        "academy-db.import.apply",
        "Academy DB import applied after human approval.",
        {"plan_id": plan_id, "approval_id": approval_id},
    )
    return {
        "status": "PASS",
        "schema_version": "academy-import-result-v1",
        "approval_id": approval_id,
        "plan_id": plan_id,
        "applied": store_counts(normalized_payload),
    }


def import_plan_root(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / ACADEMY_STATE_DIR / IMPORTS_DIR


def unapplied_import_plan_ids(profile: ProfileState) -> list[str]:
    payload = _read_json_mapping(import_plan_root(profile) / IMPORT_PLANS_FILE)
    raw_plans = payload.get("plans")
    if not isinstance(raw_plans, list):
        return []
    plan_ids: list[str] = []
    for item in raw_plans:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        plan_id = item.get("plan_id")
        if not isinstance(plan_id, str) or not isinstance(status, str):
            continue
        approval_id = item.get("approval_id")
        plan_approval_id = approval_id if isinstance(approval_id, str) else approval_id_for(plan_id)
        if status in {"APPLIED", "DENIED"}:
            continue
        if approval_is_denied(profile, plan_approval_id, plan_id):
            continue
        plan_ids.append(plan_id)
    return sorted(plan_ids)


def _read_import_source(source_path: Path, repo_root: Path) -> dict[str, JsonValue]:
    if _is_public_repo_source(source_path, repo_root) and not _is_public_safe_fixture(
        source_path,
        repo_root,
    ):
        return {
            "status": "UNSAFE",
            "error_code": "ACADEMY_IMPORT_SOURCE_UNSAFE",
            "source": "<unsafe-public-source>",
        }
    payload = _read_json_mapping(source_path)
    if not payload:
        return {"status": "ERROR", "error_code": "INVALID_ACADEMY_IMPORT_SOURCE"}
    if _is_public_safe_fixture(source_path, repo_root) and payload.get("public_safe") is not True:
        return {
            "status": "UNSAFE",
            "error_code": "ACADEMY_IMPORT_SOURCE_UNSAFE",
            "source": "<unsafe-public-source>",
        }
    source_label = (
        "<public-safe-fixture>"
        if _is_public_safe_fixture(source_path, repo_root)
        else "<private-import-source>"
    )
    return {"status": "PASS", "source": source_label, "payload": payload}


def _persist_import_plan(profile: ProfileState, plan: dict[str, JsonValue]) -> None:
    path = import_plan_root(profile) / IMPORT_PLANS_FILE
    payload = _read_json_mapping(path)
    raw_plans = payload.get("plans")
    plans = _json_object_list(raw_plans)
    plan_id = plan.get("plan_id")
    next_plans = [item for item in plans if item.get("plan_id") != plan_id]
    next_plans.append(plan)
    plan_values: list[JsonValue] = []
    plan_values.extend(next_plans)
    _write_json(path, {"plans": plan_values})


def _mark_import_plan_applied(profile: ProfileState, plan_id: str) -> None:
    path = import_plan_root(profile) / IMPORT_PLANS_FILE
    payload = _read_json_mapping(path)
    raw_plans = payload.get("plans")
    plans = _json_object_list(raw_plans)
    for plan in plans:
        if plan.get("plan_id") == plan_id:
            plan["status"] = "APPLIED"
    plan_values: list[JsonValue] = []
    plan_values.extend(plans)
    _write_json(path, {"plans": plan_values})


def _merge_import_payload(profile: ProfileState, incoming: dict[str, JsonValue]) -> None:
    store = _read_json_mapping(store_path(profile))
    for key in ("classes", "learners", "lessons"):
        current = _list_value(store.get(key))
        current.extend(_list_value(incoming.get(key)))
        store[key] = current
    store["schema_version"] = V3_SCHEMA_VERSION
    _write_json(store_path(profile), store)


def _read_json_mapping(path: Path) -> dict[str, JsonValue]:
    if not path.exists():
        return {}
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _write_json(path: Path, payload: dict[str, JsonValue]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    _ = tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)


def _list_value(value: JsonValue | None) -> list[JsonValue]:
    if isinstance(value, list):
        return value
    return []


def _json_object_list(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _is_public_repo_source(source_path: Path, repo_root: Path) -> bool:
    resolved_source = source_path.resolve()
    resolved_repo = repo_root.resolve()
    return resolved_source == resolved_repo or resolved_repo in resolved_source.parents


def _is_public_safe_fixture(source_path: Path, repo_root: Path) -> bool:
    resolved_source = source_path.resolve()
    fixture_root = (repo_root / "tests" / "fixtures" / "academy_db").resolve()
    return resolved_source.suffix == ".json" and (
        resolved_source == fixture_root or fixture_root in resolved_source.parents
    )


def _string_value(value: JsonValue | None, fallback: str) -> str:
    if isinstance(value, str):
        return value
    return fallback
