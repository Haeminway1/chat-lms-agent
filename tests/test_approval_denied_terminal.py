from __future__ import annotations

import json
from typing import TYPE_CHECKING

from tests.trace_audit_approval_support import (
    approve_interactively,
    parse_json_mapping,
    run_cli,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_denied_academy_import_approval_is_terminal(tmp_path: Path) -> None:
    import_path = tmp_path / "incoming-import.json"
    _ = import_path.write_text(
        json.dumps(
            {
                "schema_version": "academy-import-v1",
                "operation": "upsert_learners",
                "learners": [{"display_name": "Denied Learner", "class": "A"}],
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
    approval_id_value = approval_payload["approval_id"]
    assert isinstance(approval_id_value, str)
    approval_id = approval_id_value

    denied = run_cli(
        "approval",
        "deny",
        "--profile-root",
        str(tmp_path),
        "--approval-id",
        approval_id,
        "--actor",
        "human:owner",
        "--json",
    )
    assert denied.returncode == 0, denied.stderr
    denied_payload = parse_json_mapping(denied.stdout)
    assert denied_payload["status"] == "PASS"
    assert denied_payload["approval_status"] == "DENIED"

    explicit_apply = run_cli(
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
    reopened = run_cli(
        "academy-db",
        "import",
        "apply",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(import_path),
        "--json",
    )
    revived_code, revived_payload = approve_interactively(
        tmp_path,
        approval_id,
        "human:owner",
    )
    assert explicit_apply.returncode == 2
    assert json.loads(explicit_apply.stdout)["error_code"] == "APPROVAL_DENIED"
    assert reopened.returncode == 2
    assert json.loads(reopened.stdout)["error_code"] == "APPROVAL_DENIED"
    assert revived_code == 2
    assert revived_payload["error_code"] == "APPROVAL_DENIED"

    learner_count = run_cli(
        "academy-db",
        "query",
        "run",
        "--name",
        "learner-count",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    approval_list = run_cli("approval", "list", "--profile-root", str(tmp_path), "--json")
    assert json.loads(learner_count.stdout)["result"] == 0
    approval_list_payload = parse_json_mapping(approval_list.stdout)
    approvals = approval_list_payload["approvals"]
    assert isinstance(approvals, list)
    assert len(approvals) == 1
    approval_record = approvals[0]
    assert isinstance(approval_record, dict)
    assert approval_record["approval_id"] == approval_id
    assert approval_record["approval_status"] == "DENIED"

    draft_path = tmp_path / "academy-memory.json"
    draft_result = run_cli(
        "memory",
        "draft",
        "--profile-root",
        str(tmp_path),
        "--for",
        "academy-db-init",
        "--out",
        str(draft_path),
        "--json",
    )
    apply_memory = run_cli(
        "memory",
        "apply-draft",
        "--profile-root",
        str(tmp_path),
        "--from",
        str(draft_path),
        "--json",
    )
    closeout = run_cli(
        "session",
        "closeout",
        "--profile-root",
        str(tmp_path),
        "--verify-memory",
        "--json",
    )
    assert draft_result.returncode == 0, draft_result.stderr
    assert apply_memory.returncode == 0, apply_memory.stderr
    assert closeout.returncode == 0, closeout.stdout
    assert json.loads(closeout.stdout)["status"] == "PASS"
