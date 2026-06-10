from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from tests.trace_audit_approval_support import approve_interactively


def _valid_block_proposal() -> dict[str, object]:
    return {
        "id": "attendance-summary",
        "label": "Attendance Summary",
        "summary": "수업 출석 요약 카드 (synthetic attendance summary block).",
        "render_contract": {"required_keys": ["title", "items"]},
        "privacy_level": "class",
        "action_safety": {"requires_approval": True, "dry_run_default": True},
        "test_contract": {
            "command": "uv run pytest tests/test_side_panel_block_lifecycle.py -q",
        },
        "reuse_review": {
            "checked_existing": ["side-panel block list"],
            "custom_build_justification": "No attendance summary block exists in the catalog.",
        },
    }


def _scaffold(tmp_path: Path) -> str:
    proposal_path = tmp_path / "block-proposal.json"
    proposal_path.write_text(
        json.dumps(_valid_block_proposal(), ensure_ascii=False),
        encoding="utf-8",
    )
    result = _run_cli(
        "side-panel",
        "block",
        "scaffold",
        "--from",
        str(proposal_path),
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["lifecycle_state"] == "draft"
    approval_id = payload["approval_id"]
    assert isinstance(approval_id, str)
    return approval_id


def test_block_scaffold_requires_five_contracts(tmp_path: Path) -> None:
    # Given: a proposal missing most contracts.
    proposal_path = tmp_path / "bad-block.json"
    proposal_path.write_text(
        json.dumps({"id": "bare-block", "summary": "no contracts"}),
        encoding="utf-8",
    )

    # When: scaffold runs.
    result = _run_cli(
        "side-panel",
        "block",
        "scaffold",
        "--from",
        str(proposal_path),
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: every missing contract is named.
    assert result.returncode == 2, result.stdout
    payload = json.loads(result.stdout)
    assert payload["error_code"] == "INVALID_BLOCK_PROPOSAL"
    assert {
        "MISSING_RENDER_CONTRACT",
        "INVALID_PRIVACY_LEVEL",
        "MISSING_ACTION_SAFETY",
        "MISSING_TEST_CONTRACT",
        "MISSING_REUSE_REVIEW",
    } <= set(payload["errors"])


def test_block_promote_requires_teacher_approval_memory_and_evidence(
    tmp_path: Path,
) -> None:
    # Given: a scaffolded and registered block.
    approval_id = _scaffold(tmp_path)
    register = _run_cli(
        "side-panel",
        "block",
        "register",
        "--id",
        "attendance-summary",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    assert register.returncode == 0, register.stdout

    # When: promote runs before the teacher approved.
    early = _run_cli(
        "side-panel",
        "block",
        "promote",
        "--id",
        "attendance-summary",
        "--evidence",
        "tests/test_side_panel_block_lifecycle.py",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the gate demands the approval first.
    assert early.returncode == 3, early.stdout
    assert json.loads(early.stdout)["status"] == "NEEDS_APPROVAL"

    # When: the teacher approves interactively but memory is still missing.
    code, approved = approve_interactively(tmp_path, approval_id, "human:owner")
    assert code == 0, approved
    no_memory = _run_cli(
        "side-panel",
        "block",
        "promote",
        "--id",
        "attendance-summary",
        "--evidence",
        "tests/test_side_panel_block_lifecycle.py",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the memory obligation gate fires.
    assert no_memory.returncode == 5, no_memory.stdout
    no_memory_payload = json.loads(no_memory.stdout)
    assert no_memory_payload["error_code"] == "MEMORY_UPDATE_REQUIRED"
    assert no_memory_payload["required_key"] == "panel:attendance-summary"

    # When: the memory record exists and promote retries.
    upsert = _run_cli(
        "memory",
        "upsert",
        "--key",
        "panel:attendance-summary",
        "--scope",
        "durable",
        "--text",
        "출석 요약 블록 승급 결정 기록.",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    assert upsert.returncode == 0, upsert.stdout
    promote = _run_cli(
        "side-panel",
        "block",
        "promote",
        "--id",
        "attendance-summary",
        "--evidence",
        "tests/test_side_panel_block_lifecycle.py",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the block goes active and the approval is consumed (single use).
    assert promote.returncode == 0, promote.stdout
    assert json.loads(promote.stdout)["lifecycle_state"] == "active"
    listing = _run_cli(
        "side-panel",
        "block",
        "list",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    listed = json.loads(listing.stdout)
    active = listed["active_profile_blocks"]
    assert isinstance(active, list)
    assert any(
        isinstance(block, dict) and block.get("id") == "attendance-summary" for block in active
    )

    # When: a second block tries to ride the consumed approval.
    second = dict(_valid_block_proposal())
    second["id"] = "attendance-summary-2"
    second_path = tmp_path / "second.json"
    second_path.write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
    scaffold_second = _run_cli(
        "side-panel",
        "block",
        "scaffold",
        "--from",
        str(second_path),
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    assert scaffold_second.returncode == 0
    # Re-approving the consumed approval must fail terminally.
    revive_code, revive_payload = approve_interactively(tmp_path, approval_id, "human:owner")
    assert revive_code == 2
    assert revive_payload["error_code"] == "APPROVAL_CONSUMED"


def test_draft_block_never_reaches_production_list(tmp_path: Path) -> None:
    # Given: a draft block in quarantine.
    _ = _scaffold(tmp_path)

    # When: the production block list is read.
    listing = _run_cli(
        "side-panel",
        "block",
        "list",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the draft is not in the active set, and the quarantine dir exists.
    listed = json.loads(listing.stdout)
    active = listed["active_profile_blocks"]
    assert active == []
    quarantine = tmp_path / ".chat-lms-state" / "side-panel-drafts" / "attendance-summary"
    assert (quarantine / "proposal.json").exists()


def test_block_preview_validates_sample_against_contract(tmp_path: Path) -> None:
    # Given: a draft block and a sample payload missing a required key.
    _ = _scaffold(tmp_path)
    bad_sample = tmp_path / "bad-sample.json"
    bad_sample.write_text(json.dumps({"title": "출석"}), encoding="utf-8")
    good_sample = tmp_path / "good-sample.json"
    good_sample.write_text(
        json.dumps({"title": "출석", "items": ["월", "화"]}),
        encoding="utf-8",
    )

    # When: previews run.
    bad = _run_cli(
        "side-panel",
        "block",
        "preview",
        "--id",
        "attendance-summary",
        "--sample",
        str(bad_sample),
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    good = _run_cli(
        "side-panel",
        "block",
        "preview",
        "--id",
        "attendance-summary",
        "--sample",
        str(good_sample),
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the contract decides.
    assert bad.returncode == 2, bad.stdout
    assert "items" in json.dumps(json.loads(bad.stdout)["errors"])
    assert good.returncode == 0, good.stdout
    assert json.loads(good.stdout)["status"] == "PASS"


def test_block_deprecate_requires_closing_report(tmp_path: Path) -> None:
    # Given: a draft block.
    _ = _scaffold(tmp_path)

    # When: deprecate runs without a report.
    bare = _run_cli(
        "side-panel",
        "block",
        "deprecate",
        "--id",
        "attendance-summary",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the closing-report contract fires.
    assert bare.returncode == 2, bare.stdout
    assert json.loads(bare.stdout)["error_code"] == "MISSING_CLOSING_REPORT"

    # When: a report is supplied.
    closed = _run_cli(
        "side-panel",
        "block",
        "deprecate",
        "--id",
        "attendance-summary",
        "--report",
        "시도했으나 출석 요약은 기존 metric_grid로 충분함.",
        "--profile-root",
        str(tmp_path),
        "--json",
    )

    # Then: the block closes with the report persisted.
    assert closed.returncode == 0, closed.stdout
    explain = _run_cli(
        "side-panel",
        "block",
        "explain",
        "--id",
        "attendance-summary",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    explained = json.loads(explain.stdout)
    assert "metric_grid" in explained["block"]["closing_report"]


def test_closeout_surfaces_open_blocks_advisory(tmp_path: Path) -> None:
    # Given: an open draft block and an otherwise clean profile.
    _ = _scaffold(tmp_path)

    # When: the session closes.
    closeout = _run_cli(
        "session",
        "closeout",
        "--profile-root",
        str(tmp_path),
        "--verify-memory",
        "--json",
    )

    # Then: closeout stays advisory (PASS) but names the open block.
    assert closeout.returncode == 0, closeout.stdout
    payload = json.loads(closeout.stdout)
    assert payload["status"] == "PASS"
    assert payload["open_blocks"] == ["attendance-summary"]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
        input="",
    )
