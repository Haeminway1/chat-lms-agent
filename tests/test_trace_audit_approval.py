from __future__ import annotations

import json
from typing import TYPE_CHECKING

from tests.trace_audit_approval_support import (
    assert_consumed_approval_is_terminal,
    assert_import_plan_stays_applied_after_reuse_rejection,
    assert_private_audit_retains_planned_and_applied_records,
    assert_private_records_are_redacted,
    assert_public_output_redacted,
    parse_json_mapping,
    run_cli,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_academy_import_apply_requires_human_approval_and_redacts_audit(
    tmp_path: Path,
) -> None:
    import_path = tmp_path / "incoming-import.json"
    leaked_tmp_path = tmp_path / "private" / "raw-stdout.txt"
    _ = import_path.write_text(
        json.dumps(
            {
                "schema_version": "academy-import-v1",
                "operation": "upsert_learners",
                "learners": [{"display_name": "Minji Kim", "class": "A"}],
                "environment": "SECRET=top-secret-token",
                "raw_stdout": f"raw stdout: imported Minji Kim from {leaked_tmp_path}",
                "tmp_path": str(leaked_tmp_path),
            },
        ),
        encoding="utf-8",
    )
    init_result = run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")
    assert init_result.returncode == 0, init_result.stderr

    needs_approval = run_cli(
        "academy-db",
        "import",
        "apply",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(import_path),
        "--json",
    )

    assert needs_approval.returncode == 3, needs_approval.stderr
    approval_payload = parse_json_mapping(needs_approval.stdout)
    assert approval_payload["status"] == "NEEDS_APPROVAL"
    assert approval_payload["schema_version"] == "approval-request-v1"
    approval_id_value = approval_payload["approval_id"]
    assert isinstance(approval_id_value, str)
    approval_id = approval_id_value
    assert_public_output_redacted(needs_approval.stdout, tmp_path)
    assert_private_records_are_redacted(tmp_path)

    self_approval = run_cli(
        "approval",
        "approve",
        "--profile-root",
        str(tmp_path),
        "--approval-id",
        approval_id,
        "--actor",
        "codex_desktop_agent",
        "--json",
    )

    assert self_approval.returncode == 2
    self_approval_payload = parse_json_mapping(self_approval.stdout)
    assert self_approval_payload["status"] == "REJECTED"
    assert self_approval_payload["error_code"] == "SELF_APPROVAL_REJECTED"

    human_approval = run_cli(
        "approval",
        "approve",
        "--profile-root",
        str(tmp_path),
        "--approval-id",
        approval_id,
        "--actor",
        "human:owner",
        "--json",
    )

    assert human_approval.returncode == 0, human_approval.stderr
    human_approval_payload = parse_json_mapping(human_approval.stdout)
    assert human_approval_payload["status"] == "PASS"
    assert human_approval_payload["schema_version"] == "approval-v1"
    assert human_approval_payload["approval_status"] == "APPROVED"

    applied = run_cli(
        "academy-db",
        "import",
        "apply",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(import_path),
        "--approval-id",
        approval_id,
        "--json",
    )

    assert applied.returncode == 0, applied.stderr
    applied_payload = parse_json_mapping(applied.stdout)
    assert applied_payload["status"] == "PASS"
    assert applied_payload["schema_version"] == "academy-import-result-v1"
    assert applied_payload["approval_id"] == approval_id
    assert_public_output_redacted(applied.stdout, tmp_path)
    assert_private_records_are_redacted(tmp_path)

    reused = run_cli(
        "academy-db",
        "import",
        "apply",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(import_path),
        "--approval-id",
        approval_id,
        "--json",
    )

    assert reused.returncode == 2
    reused_payload = parse_json_mapping(reused.stdout)
    assert reused_payload["status"] == "ERROR"
    assert reused_payload["error_code"] == "APPROVAL_CONSUMED"
    assert_public_output_redacted(reused.stdout, tmp_path)
    assert_private_records_are_redacted(tmp_path)
    assert_import_plan_stays_applied_after_reuse_rejection(tmp_path)
    assert_private_audit_retains_planned_and_applied_records(tmp_path)

    assert_consumed_approval_is_terminal(tmp_path, import_path, approval_id)
