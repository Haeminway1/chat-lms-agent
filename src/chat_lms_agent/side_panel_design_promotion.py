from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.hosts import active_host
from chat_lms_agent.side_panel_design_verify_contract import artifact_sha256
from chat_lms_agent.state import STATE_DIR, read_state_mapping, redact_text, write_state_mapping

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chat_lms_agent.state import JsonValue, ProfileState

_VIEWER_STATE_FILE: Final = "side-panel-design-viewers.json"
_BACKUP_DIR: Final = "side-panel-viewer-backups"
_ARTIFACT_NAME: Final = "artifact.html"


@dataclass(frozen=True, slots=True)
class DesignEvidence:
    path: Path
    artifact_sha256: str
    timestamp_utc: str
    view: str


@dataclass(frozen=True, slots=True)
class InstallResult:
    installed_viewer: Path
    backup_path: Path | None
    installed_at: str
    artifact_sha256: str


@dataclass(frozen=True, slots=True)
class InstalledDesignViewer:
    view: str
    viewer_path: Path
    artifact_sha256: str
    verify_evidence_path: Path | None
    verify_evidence_timestamp_utc: str


@dataclass(frozen=True, slots=True)
class ViewerStateParts:
    record: Mapping[str, object]
    evidence: DesignEvidence
    viewer: Path
    backup_path: Path | None
    installed_at: str


def is_design_block(record: Mapping[str, object]) -> bool:
    render_contract = record.get("render_contract")
    if not isinstance(render_contract, dict):
        return False
    contract = cast("dict[object, object]", render_contract)
    return contract.get("artifact") == _ARTIFACT_NAME and isinstance(contract.get("view"), str)


def validate_design_evidence(
    profile: ProfileState,
    record: Mapping[str, object],
    evidence: str,
) -> tuple[int, dict[str, JsonValue] | DesignEvidence]:
    artifact = design_artifact_path(profile, _record_id(record))
    evidence_path = _evidence_path(profile, evidence)
    payload = _read_json_object(evidence_path)
    reason = _evidence_failure_reason(artifact, record, payload)
    if reason is not None:
        return 5, _evidence_required(reason)
    expected_sha = artifact_sha256(artifact)
    view = _record_view(record)
    timestamp = _payload_string(payload, "timestamp_utc")
    return 0, DesignEvidence(
        path=evidence_path,
        artifact_sha256=expected_sha,
        timestamp_utc=timestamp,
        view=view,
    )


def install_design_viewer(
    profile: ProfileState,
    record: Mapping[str, object],
    evidence: DesignEvidence,
) -> InstallResult:
    artifact = design_artifact_path(profile, _record_id(record))
    viewer = profile.root / active_host().workspace_dirname / "scripts" / "lesson_panel_view.html"
    viewer.parent.mkdir(parents=True, exist_ok=True)
    installed_at = datetime.now(tz=UTC).isoformat()
    backup_path = _backup_existing_viewer(profile, viewer, installed_at)
    _ = shutil.copyfile(artifact, viewer)
    _write_viewer_state(
        profile,
        ViewerStateParts(
            record=record,
            evidence=evidence,
            viewer=viewer,
            backup_path=backup_path,
            installed_at=installed_at,
        ),
    )
    return InstallResult(
        installed_viewer=viewer,
        backup_path=backup_path,
        installed_at=installed_at,
        artifact_sha256=evidence.artifact_sha256,
    )


def restore_design_viewer(
    profile: ProfileState,
    record: Mapping[str, object],
) -> tuple[bool, Path | None]:
    state = _viewer_record(profile, _record_id(record))
    if state is None:
        return False, None
    backup = state.get("backup_path")
    if not isinstance(backup, str) or not backup:
        return False, None
    backup_path = Path(backup)
    if not backup_path.exists():
        return False, None
    viewer = profile.root / active_host().workspace_dirname / "scripts" / "lesson_panel_view.html"
    viewer.parent.mkdir(parents=True, exist_ok=True)
    _ = shutil.copyfile(backup_path, viewer)
    return True, backup_path


def design_promotion_payload(result: InstallResult) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "installed": True,
        "installed_viewer": redact_text(str(result.installed_viewer)),
        "installed_at": result.installed_at,
        "artifact_sha256": result.artifact_sha256,
    }
    if result.backup_path is not None:
        payload["backup_path"] = redact_text(str(result.backup_path))
    return payload


def design_restore_payload(*, restored: bool, backup_path: Path | None) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {"restored": restored}
    if backup_path is not None:
        payload["restored_from_backup"] = redact_text(str(backup_path))
    return payload


def design_artifact_path(profile: ProfileState, block_id: str) -> Path:
    return profile.root / STATE_DIR / "side-panel-drafts" / block_id / _ARTIFACT_NAME


def installed_design_viewers(profile: ProfileState) -> tuple[InstalledDesignViewer, ...]:
    payload = read_state_mapping(profile, _VIEWER_STATE_FILE)
    viewers = payload.get("viewers")
    if not isinstance(viewers, dict):
        return ()
    installed: list[InstalledDesignViewer] = []
    for view, raw_item in viewers.items():
        if not isinstance(raw_item, dict):
            continue
        item = cast("dict[str, JsonValue]", raw_item)
        viewer_path = _path_from_payload(item, "viewer_path")
        timestamp = _payload_string(item, "verify_evidence_timestamp_utc")
        artifact_hash = _payload_string(item, "artifact_sha256")
        if viewer_path is None or not timestamp or not artifact_hash:
            continue
        installed.append(
            InstalledDesignViewer(
                view=view,
                viewer_path=viewer_path,
                artifact_sha256=artifact_hash,
                verify_evidence_path=_path_from_payload(item, "verify_evidence_path"),
                verify_evidence_timestamp_utc=timestamp,
            ),
        )
    return tuple(installed)


def _backup_existing_viewer(profile: ProfileState, viewer: Path, installed_at: str) -> Path | None:
    if not viewer.exists():
        return None
    backup_dir = profile.root / STATE_DIR / _BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = installed_at.replace(":", "").replace("+", "Z")
    backup = backup_dir / f"lesson_panel_view.{stamp}.html"
    _ = shutil.copyfile(viewer, backup)
    return backup


def _write_viewer_state(profile: ProfileState, parts: ViewerStateParts) -> None:
    payload = read_state_mapping(profile, _VIEWER_STATE_FILE)
    viewers = payload.get("viewers")
    if not isinstance(viewers, dict):
        viewers = {}
    viewers[parts.evidence.view] = {
        "block_id": _record_id(parts.record),
        "viewer_path": str(parts.viewer),
        "backup_path": "" if parts.backup_path is None else str(parts.backup_path),
        "artifact_sha256": parts.evidence.artifact_sha256,
        "verify_evidence_path": str(parts.evidence.path),
        "verify_evidence_timestamp_utc": parts.evidence.timestamp_utc,
        "installed_at": parts.installed_at,
    }
    write_state_mapping(profile, _VIEWER_STATE_FILE, {"viewers": viewers})


def _viewer_record(profile: ProfileState, block_id: str) -> dict[str, JsonValue] | None:
    payload = read_state_mapping(profile, _VIEWER_STATE_FILE)
    viewers = payload.get("viewers")
    if not isinstance(viewers, dict):
        return None
    for item in viewers.values():
        if isinstance(item, dict) and item.get("block_id") == block_id:
            return item
    return None


def _evidence_required(reason: str) -> dict[str, JsonValue]:
    return {
        "status": "BLOCKED",
        "error_code": "DESIGN_VERIFY_EVIDENCE_REQUIRED",
        "message": reason,
        "repair_action": (
            "side-panel design verify --artifact <artifact> --view <view> --mode all --json"
        ),
    }


def _evidence_path(profile: ProfileState, evidence: str) -> Path:
    path = Path(evidence)
    if path.is_absolute():
        return path
    return profile.repo_root / path


def _read_json_object(path: Path) -> dict[str, JsonValue] | None:
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _timestamp_is_usable(raw_timestamp: str) -> bool:
    try:
        parsed = datetime.fromisoformat(raw_timestamp)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        return False
    return parsed <= datetime.now(tz=UTC)


def _evidence_failure_reason(
    artifact: Path,
    record: Mapping[str, object],
    payload: dict[str, JsonValue] | None,
) -> str | None:
    reason: str | None = None
    if not artifact.exists():
        reason = "generated artifact is missing"
    elif payload is None:
        reason = "verify evidence JSON could not be read"
    elif payload.get("status") != "PASS":
        reason = "verify evidence status is not PASS"
    elif not _nested_status_is_pass(payload, "lint"):
        reason = "lint PASS evidence is required"
    elif not _nested_status_is_pass(payload, "verify"):
        reason = "verify PASS evidence is required"
    elif payload.get("artifact_sha256") != artifact_sha256(artifact):
        reason = "verify evidence sha256 does not match artifact"
    elif payload.get("view") != _record_view(record):
        reason = "verify evidence view does not match artifact"
    elif not _covers_panel(payload):
        reason = "verify evidence must cover panel mode"
    elif not _timestamp_is_usable(_payload_string(payload, "timestamp_utc")):
        reason = "verify evidence timestamp is invalid"
    return reason


def _nested_status_is_pass(payload: dict[str, JsonValue], key: str) -> bool:
    nested = payload.get(key)
    return isinstance(nested, dict) and nested.get("status") == "PASS"


def _covers_panel(payload: dict[str, JsonValue]) -> bool:
    checked_modes = payload.get("checked_modes")
    return isinstance(checked_modes, list) and "panel" in checked_modes


def _payload_string(payload: dict[str, JsonValue] | None, key: str) -> str:
    if payload is None:
        return ""
    value = payload.get(key)
    return value if isinstance(value, str) else ""


def _path_from_payload(payload: dict[str, JsonValue], key: str) -> Path | None:
    raw_path = _payload_string(payload, key)
    return Path(raw_path) if raw_path else None


def _record_id(record: Mapping[str, object]) -> str:
    block_id = record.get("id")
    return block_id if isinstance(block_id, str) else ""


def _record_view(record: Mapping[str, object]) -> str:
    render_contract = record.get("render_contract")
    if isinstance(render_contract, dict):
        contract = cast("dict[object, object]", render_contract)
        view = contract.get("view")
        if isinstance(view, str):
            return view
    return ""
