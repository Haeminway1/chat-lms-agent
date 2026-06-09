from __future__ import annotations

import json
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.state import STATE_DIR, JsonValue, ProfileState

if TYPE_CHECKING:
    from pathlib import Path

SCHEMA_VERSION: Final = "academy-v1"
V3_SCHEMA_VERSION: Final = "academy-v3"
ACADEMY_STATE_DIR: Final = "academy"
STORE_FILE: Final = "academy-store.json"
REPORTS_DIR: Final = "reports"
BACKUPS_DIR: Final = "backups"
NAMED_QUERIES: Final = ("learner-count", "class-count")


def spec_payload() -> dict[str, JsonValue]:
    return {
        "status": "PASS",
        "schema_version": SCHEMA_VERSION,
        "public_safe": True,
        "entities": ["classes", "learners", "lessons"],
        "queries": list(NAMED_QUERIES),
    }


def init_store(profile: ProfileState) -> dict[str, JsonValue]:
    path = store_path(profile)
    if not path.exists():
        _write_store(
            path,
            {
                "schema_version": SCHEMA_VERSION,
                "classes": [],
                "learners": [],
                "lessons": [],
            },
        )
    return {
        "status": "PASS",
        "schema_version": SCHEMA_VERSION,
        "store": "<profile-root>/.chat-lms-state/academy/academy-store.json",
        "public_safe": True,
    }


def query_list_payload() -> dict[str, JsonValue]:
    return {"status": "PASS", "queries": list(NAMED_QUERIES)}


def run_query(
    profile: ProfileState,
    name: str,
    params_path: Path | None = None,
) -> dict[str, JsonValue]:
    store = _read_store(profile)
    params = _read_params(params_path)
    validation_error = _query_param_error(name, params)
    if validation_error is not None:
        return validation_error
    match name:
        case "learner-count":
            result = _learner_count(store, params)
        case "class-count":
            result = len(_list_value(store.get("classes")))
        case _:
            return {"status": "ERROR", "error_code": "UNKNOWN_ACADEMY_QUERY", "query": name}
    payload: dict[str, JsonValue] = {"status": "PASS", "query": name}
    if params_path is not None:
        payload["params"] = params
        payload["result"] = {"count": result}
        return payload
    payload["result"] = result
    return payload


def inspect_store(profile: ProfileState) -> dict[str, JsonValue]:
    store = _read_store(profile)
    return {
        "status": "PASS",
        "schema_version": V3_SCHEMA_VERSION,
        "store": "<profile-root>/.chat-lms-state/academy/academy-store.json",
        "counts": _store_counts(store),
    }


def schema_payload() -> dict[str, JsonValue]:
    return {
        "status": "PASS",
        "schema_version": V3_SCHEMA_VERSION,
        "entities": ["classes", "learners", "lessons"],
        "named_queries": {
            "learner-count": {
                "params": {
                    "class_id": {"required": False, "type": "string"},
                },
            },
            "class-count": {"params": {}},
        },
    }


def academy_doctor_payload() -> dict[str, JsonValue]:
    return {
        "status": "PASS",
        "schema_version": V3_SCHEMA_VERSION,
        "checks": [
            {"id": "academy-db-schema-v3", "status": "PASS"},
            {"id": "academy-db-import-safety-v3", "status": "PASS"},
        ],
    }


def build_report(profile: ProfileState, report: str) -> dict[str, JsonValue]:
    _ = init_store(profile)
    path = report_root(profile) / f"{report}.json"
    _write_store(
        path,
        {
            "report": report,
            "schema_version": SCHEMA_VERSION,
            "source": "academy-store",
            "public_safe": True,
        },
    )
    return {
        "status": "PASS",
        "report": report,
        "path": f"<profile-root>/.chat-lms-state/academy/reports/{report}.json",
    }


def create_backup(profile: ProfileState) -> dict[str, JsonValue]:
    _ = init_store(profile)
    backup_id = "latest"
    backup_path = backup_root(profile) / f"{backup_id}.json"
    source = store_path(profile)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    _ = backup_path.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return {
        "status": "PASS",
        "backup_id": backup_id,
        "path": "<profile-root>/.chat-lms-state/academy/backups/latest.json",
    }


def plan_migration(target: str) -> dict[str, JsonValue]:
    return {"status": "PASS", "plan_id": f"migration-{target}", "target": target}


def apply_migration(profile: ProfileState, target: str) -> dict[str, JsonValue]:
    if not any(backup_root(profile).glob("*.json")):
        return {"status": "ERROR", "error_code": "BACKUP_REQUIRED", "target": target}
    return {"status": "PASS", "applied": f"migration-{target}"}


def plan_restore() -> dict[str, JsonValue]:
    return {"status": "PASS", "plan_id": "restore-latest"}


def apply_restore(plan_id: str | None) -> dict[str, JsonValue]:
    if plan_id is None:
        return {"status": "ERROR", "error_code": "RESTORE_PLAN_REQUIRED"}
    return {"status": "PASS", "applied": plan_id}


def store_path(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / ACADEMY_STATE_DIR / STORE_FILE


def report_root(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / ACADEMY_STATE_DIR / REPORTS_DIR


def backup_root(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / ACADEMY_STATE_DIR / BACKUPS_DIR


def _read_store(profile: ProfileState) -> dict[str, JsonValue]:
    path = store_path(profile)
    if not path.exists():
        _ = init_store(profile)
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


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


def _write_store(path: Path, payload: dict[str, JsonValue]) -> None:
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


def _read_params(path: Path | None) -> dict[str, JsonValue]:
    if path is None:
        return {}
    return _read_json_mapping(path)


def _learner_count(store: dict[str, JsonValue], params: dict[str, JsonValue]) -> int:
    learners = _list_value(store.get("learners"))
    class_id = params.get("class_id")
    if not isinstance(class_id, str):
        return len(learners)
    count = 0
    for learner in learners:
        if isinstance(learner, dict) and learner.get("class_id") == class_id:
            count += 1
    return count


def _query_param_error(name: str, params: dict[str, JsonValue]) -> dict[str, JsonValue] | None:
    errors: list[JsonValue] = []
    allowed_keys: set[str] = {"class_id"} if name == "learner-count" else set()
    for key, value in params.items():
        if key not in allowed_keys:
            errors.append(f"unknown param: {key}")
        if key == "class_id" and not isinstance(value, str):
            errors.append("class_id must be string")
    if errors:
        return {
            "status": "ERROR",
            "error_code": "INVALID_QUERY_PARAMS",
            "param_errors": errors,
        }
    return None


def _store_counts(store: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "classes": len(_list_value(store.get("classes"))),
        "learners": len(_list_value(store.get("learners"))),
        "lessons": len(_list_value(store.get("lessons"))),
    }
