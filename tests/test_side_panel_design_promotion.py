from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from chat_lms_agent.side_panel_design_verify_contract import (
    VerifyEvidenceParts,
    build_verify_evidence,
)
from tests.trace_audit_approval_support import approve_interactively

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


def test_design_promote_requires_verify_evidence_before_install(tmp_path: Path) -> None:
    # Given: a registered generated design block with an artifact in quarantine.
    block_id = "design-class-overview-gate"
    _approval_id, _artifact = _scaffold_registered_design_block(
        tmp_path,
        block_id,
        "<html>new</html>\n",
    )
    viewer = tmp_path / "codex-workspace" / "scripts" / "class_overview_view.html"

    # When: promote runs without evidence and then with a lint-only evidence file.
    missing = _run_cli(
        "side-panel",
        "block",
        "promote",
        "--id",
        block_id,
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    lint_only = tmp_path / "lint-only.json"
    _ = lint_only.write_text(
        json.dumps({"status": "PASS", "lint": {"status": "PASS"}}, ensure_ascii=False),
        encoding="utf-8",
    )
    invalid = _run_cli(
        "side-panel",
        "block",
        "promote",
        "--id",
        block_id,
        "--evidence",
        str(lint_only),
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: existing missing-evidence semantics remain and invalid design evidence blocks install.
    assert missing.returncode == 2, missing.stdout
    assert json.loads(missing.stdout)["error_code"] == "MISSING_PROMOTE_EVIDENCE"
    assert invalid.returncode == 5, invalid.stdout
    invalid_payload = _json_object(invalid.stdout)
    assert invalid_payload["status"] == "BLOCKED"
    assert invalid_payload["error_code"] == "DESIGN_VERIFY_EVIDENCE_REQUIRED"
    assert not viewer.exists()


def test_design_promote_installs_viewer_with_backup_and_deprecate_restores(
    tmp_path: Path,
) -> None:
    # Given: a registered generated design block, previous viewer, approval, memory, and evidence.
    block_id = "design-class-overview-promote"
    new_html = "<!doctype html><html><body>D4 promoted viewer</body></html>\n"
    approval_id, artifact = _scaffold_registered_design_block(tmp_path, block_id, new_html)
    viewer = tmp_path / "codex-workspace" / "scripts" / "class_overview_view.html"
    viewer.parent.mkdir(parents=True)
    previous_html = "<!doctype html><html><body>previous viewer</body></html>\n"
    _ = viewer.write_text(previous_html, encoding="utf-8")
    evidence = tmp_path / "verify-evidence.json"
    _write_valid_evidence(artifact, evidence)
    memory = _run_cli(
        "memory",
        "upsert",
        "--key",
        f"panel:{block_id}",
        "--scope",
        "durable",
        "--text",
        "Generated class overview viewer approved with verifier evidence.",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # When: the first promote records the approval request, then approval allows install.
    early = _run_cli(
        "side-panel",
        "block",
        "promote",
        "--id",
        block_id,
        "--evidence",
        str(evidence),
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    approve_code, approve_payload = approve_interactively(tmp_path, approval_id, "human:owner")
    promote = _run_cli(
        "side-panel",
        "block",
        "promote",
        "--id",
        block_id,
        "--evidence",
        str(evidence),
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    backup_files = sorted(
        (tmp_path / ".chat-lms-state" / "side-panel-viewer-backups").glob("*.html"),
    )

    # Then: promotion installs with a backup and deprecate restores the previous viewer.
    assert early.returncode == 3, early.stdout
    assert approve_code == 0, approve_payload
    assert memory.returncode == 0, memory.stdout
    assert promote.returncode == 0, promote.stdout
    promote_payload = _json_object(promote.stdout)
    assert promote_payload["lifecycle_state"] == "active"
    assert promote_payload["installed"] is True
    assert promote_payload["artifact_sha256"]
    assert str(tmp_path) not in promote.stdout
    assert viewer.read_text(encoding="utf-8") == new_html
    assert len(backup_files) == 1
    assert backup_files[0].read_text(encoding="utf-8") == previous_html
    doctor = _run_cli("doctor", "--profile-root", str(tmp_path), "--json")
    assert doctor.returncode == 0, doctor.stdout
    verify_check = _checks_by_id(doctor)["side_panel_viewers_verify_evidence"]
    assert verify_check["status"] == "PASS"

    deprecated = _run_cli(
        "side-panel",
        "block",
        "deprecate",
        "--id",
        block_id,
        "--report",
        "Verifier-backed generated viewer replaced by previous viewer after test.",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    assert deprecated.returncode == 0, deprecated.stdout
    deprecated_payload = _json_object(deprecated.stdout)
    assert deprecated_payload["lifecycle_state"] == "deprecated"
    assert deprecated_payload["restored"] is True
    assert viewer.read_text(encoding="utf-8") == previous_html


def _scaffold_registered_design_block(
    tmp_path: Path,
    block_id: str,
    artifact_html: str,
) -> tuple[str, Path]:
    proposal_path = tmp_path / f"{block_id}.json"
    _ = proposal_path.write_text(
        json.dumps(_design_block_proposal(block_id), ensure_ascii=False),
        encoding="utf-8",
    )
    scaffold = _run_cli(
        "side-panel",
        "block",
        "scaffold",
        "--from",
        str(proposal_path),
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    register = _run_cli(
        "side-panel",
        "block",
        "register",
        "--id",
        block_id,
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    artifact = tmp_path / ".chat-lms-state" / "side-panel-drafts" / block_id / "artifact.html"
    _ = artifact.write_text(artifact_html, encoding="utf-8")
    assert scaffold.returncode == 0, scaffold.stdout
    assert register.returncode == 0, register.stdout
    approval_id = _json_string(_json_object(scaffold.stdout)["approval_id"])
    return approval_id, artifact


def _design_block_proposal(block_id: str) -> dict[str, JsonValue]:
    return {
        "id": block_id,
        "label": "Generated Class Overview Viewer",
        "summary": "Generated class overview side-panel viewer.",
        "render_contract": {
            "view": "class_overview",
            "modes": ["panel", "fullscreen"],
            "artifact": "artifact.html",
            "api_prefix": "/api/",
        },
        "privacy_level": "side_panel",
        "action_safety": {"requires_approval": True, "dry_run_default": True},
        "test_contract": {"verify": "side-panel design verify --artifact artifact.html"},
        "reuse_review": {
            "checked_existing": ["side-panel block list"],
            "custom_build_justification": "Synthetic generated design promotion test.",
        },
    }


def _write_valid_evidence(artifact: Path, evidence: Path) -> None:
    payload = build_verify_evidence(
        VerifyEvidenceParts(
            artifact_path=artifact,
            view="class_overview",
            mode="all",
            checked_modes=("panel", "fullscreen"),
            lint_payload={"status": "PASS", "errors": []},
            checks=[
                {"id": "fixture_a_markers", "status": "PASS"},
                {"id": "fixture_b_replaces_a", "status": "PASS"},
                {"id": "panel_horizontal_scroll", "status": "PASS"},
                {"id": "fullscreen_horizontal_scroll", "status": "PASS"},
            ],
        ),
    )
    _ = evidence.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        input="",
        capture_output=True,
        check=False,
        text=True,
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _json_object(value: str | JsonValue) -> dict[str, JsonValue]:
    payload = cast("JsonValue", json.loads(value)) if isinstance(value, str) else value
    assert isinstance(payload, dict)
    return payload


def _json_string(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _checks_by_id(
    result: subprocess.CompletedProcess[str],
) -> dict[str, dict[str, JsonValue]]:
    payload = _json_object(result.stdout)
    raw_checks = payload["checks"]
    assert isinstance(raw_checks, list)
    checks: dict[str, dict[str, JsonValue]] = {}
    for item in raw_checks:
        if not isinstance(item, dict):
            continue
        check = cast("dict[str, JsonValue]", item)
        check_id = check.get("id")
        if isinstance(check_id, str):
            checks[check_id] = check
    return checks
