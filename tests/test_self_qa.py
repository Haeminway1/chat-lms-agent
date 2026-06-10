from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chat_lms_agent.self_qa import (
    QA_LEDGER_MAX_BYTES,
    append_qa_record,
    install_id,
    list_qa_records,
    set_qa_consent,
)
from chat_lms_agent.state import ProfileState


def _profile(tmp_path: Path) -> ProfileState:
    return ProfileState(root=tmp_path / "profile", repo_root=_repo_root())


def test_no_writes_without_consent(tmp_path: Path) -> None:
    # Given: consent has never been answered.
    profile = _profile(tmp_path)

    # When: an anomaly append is attempted.
    written = append_qa_record(profile, "hook_anomaly", error_code="INVALID_HOOK_PAYLOAD")

    # Then: nothing is written anywhere.
    assert written is False
    assert list_qa_records(profile)["records"] == []


def test_consent_grant_enables_bounded_writes(tmp_path: Path) -> None:
    # Given: the teacher granted consent.
    profile = _profile(tmp_path)
    set_qa_consent(profile, "granted")

    # When: an anomaly is appended.
    written = append_qa_record(
        profile,
        "hook_anomaly",
        error_code="INVALID_HOOK_PAYLOAD",
        summary="hook stdin must be valid JSON",
    )

    # Then: the record is listed with only the fixed schema fields.
    assert written is True
    records = list_qa_records(profile)["records"]
    assert isinstance(records, list)
    assert len(records) == 1
    record = records[0]
    assert isinstance(record, dict)
    assert record["record_kind"] == "hook_anomaly"
    assert record["error_code"] == "INVALID_HOOK_PAYLOAD"
    assert set(record) <= {
        "record_kind",
        "error_code",
        "summary",
        "tool_name",
        "session_id",
        "created_at",
    }


def test_schema_structurally_rejects_learner_fields(tmp_path: Path) -> None:
    # Given/When/Then: there is no field a learner name could ride in on.
    profile = _profile(tmp_path)
    set_qa_consent(profile, "granted")
    with pytest.raises(TypeError):
        append_qa_record(  # type: ignore[call-arg]
            profile,
            "hook_anomaly",
            learner_name="민지",
        )


def test_denied_consent_blocks_writes(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    set_qa_consent(profile, "denied")
    assert append_qa_record(profile, "hook_anomaly") is False


def test_ledger_rotation_stays_bounded(tmp_path: Path) -> None:
    # Given: far more records than the cap can hold.
    profile = _profile(tmp_path)
    set_qa_consent(profile, "granted")
    for index in range(3000):
        _ = append_qa_record(profile, "hook_anomaly", summary=f"probe {index} " + "x" * 120)

    # Then: the ledger never exceeds its byte cap and keeps the newest records.
    ledger = tmp_path / "profile" / ".chat-lms-state" / "qa-ledger.jsonl"
    assert ledger.stat().st_size <= QA_LEDGER_MAX_BYTES
    records = list_qa_records(profile)["records"]
    assert isinstance(records, list)
    last = records[-1]
    assert isinstance(last, dict)
    summary = last["summary"]
    assert isinstance(summary, str)
    assert "probe 2999" in summary


def test_install_id_is_stable_and_exclusive(tmp_path: Path) -> None:
    # Given: a fresh profile.
    profile = _profile(tmp_path)

    # When: the install id is requested twice.
    first = install_id(profile)
    second = install_id(profile)

    # Then: it is created once and stays stable.
    assert first == second
    assert len(first) >= 8
    id_path = tmp_path / "profile" / ".chat-lms-state" / "install-id"
    assert id_path.read_text(encoding="utf-8").strip() == first


def test_invalid_hook_payload_appends_qa_record() -> None:
    # Given: consent granted in the hermetic env profile.
    repo_root = _repo_root()
    profile = ProfileState(
        root=Path(os.environ["CHAT_LMS_AGENT_PROFILE_ROOT"]),
        repo_root=repo_root,
    )
    set_qa_consent(profile, "granted")

    # When: a malformed hook payload arrives.
    result = _run_cli("{bad json", "hook", "post-tool-use", "--json")
    assert result.returncode == 2

    # Then: the anomaly lands in the self-QA ledger.
    records = list_qa_records(profile)["records"]
    assert isinstance(records, list)
    codes = {record.get("error_code") for record in records if isinstance(record, dict)}
    assert "INVALID_HOOK_PAYLOAD" in codes


def test_cli_consent_and_list() -> None:
    # Given/When: the teacher grants consent and lists records via CLI.
    grant = _run_cli("", "harness", "qa", "consent", "--grant", "--json")
    listing = _run_cli("", "harness", "qa", "list", "--json")

    # Then: both verbs answer with the contract.
    assert grant.returncode == 0, grant.stdout
    assert json.loads(grant.stdout)["consent"] == "granted"
    assert listing.returncode == 0, listing.stdout
    assert json.loads(listing.stdout)["status"] == "PASS"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(stdin: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        input=stdin,
        capture_output=True,
        check=False,
        text=True,
    )
