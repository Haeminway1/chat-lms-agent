"""External Integration Module framework — axes, registry, outward gate."""

from __future__ import annotations

from pathlib import Path

from chat_lms_agent.approvals import approve_request
from chat_lms_agent.integration_modules import (
    INTEGRATION_MODULES,
    consume_outward_send,
    evaluate_outward_send,
)
from chat_lms_agent.state import ProfileState, resolve_profile_state

_CAPABILITY_TIERS = {"official_api", "official_cli", "browser_automation", "self_hosted"}
_SETUP_MODELS = {"embedded_consent", "per_user_account", "per_user_channel", "per_user_login"}
_OUTWARD = {"none", "self_account", "third_party"}


def test_every_module_declares_valid_axes() -> None:
    by_id = {module.module_id: module for module in INTEGRATION_MODULES}

    assert {"gws", "classcard", "sms", "kakao"} <= set(by_id)
    for module in INTEGRATION_MODULES:
        assert module.capability_tier in _CAPABILITY_TIERS, module.module_id
        assert module.setup_model in _SETUP_MODELS, module.module_id
        assert set(module.outward_writes) <= _OUTWARD, module.module_id
        if "third_party" in module.outward_writes:
            assert module.approval_required, (
                f"{module.module_id}: third_party writes must be approval-gated"
            )
    # classcard uploads to the teacher's own account — not third_party.
    assert by_id["classcard"].outward_writes == ("self_account",)
    assert "third_party" in by_id["sms"].outward_writes
    assert "third_party" in by_id["kakao"].outward_writes


def test_contract_doc_exists_with_axes_and_rule() -> None:
    doc = (_repo_root() / "docs" / "external-integration-contract.md").read_text(
        encoding="utf-8",
    )
    for anchor in ("capability_tier", "setup_model", "outward_writes", "third_party"):
        assert anchor in doc


def test_outward_gate_lifecycle(tmp_path: Path) -> None:
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)

    # 1) No approval id → NEEDS_APPROVAL with a stable id and the recipient
    #    bound into the operation text.
    first = evaluate_outward_send(
        profile,
        None,
        kind="sms_send",
        recipient="01000000000",
        summary="6월 시험 안내",
        error_prefix="SMS",
    )
    assert first.decision == "needs_approval"
    assert first.exit_code == 3
    assert first.payload is not None
    assert "01000000000" in str(first.payload["operation"])
    approval_id = str(first.payload["approval_id"])

    # 2) A different recipient never matches that approval.
    other = evaluate_outward_send(
        profile,
        approval_id,
        kind="sms_send",
        recipient="01099999999",
        summary="6월 시험 안내",
        error_prefix="SMS",
    )
    assert other.decision == "needs_approval"

    # 3) Approved → proceed; consume; then the same id is blocked.
    _ = approve_request(profile, approval_id, "teacher")
    gate = evaluate_outward_send(
        profile,
        approval_id,
        kind="sms_send",
        recipient="01000000000",
        summary="6월 시험 안내",
        error_prefix="SMS",
    )
    assert gate.decision == "proceed"
    consume_outward_send(profile, gate)
    blocked = evaluate_outward_send(
        profile,
        approval_id,
        kind="sms_send",
        recipient="01000000000",
        summary="6월 시험 안내",
        error_prefix="SMS",
    )
    assert blocked.decision == "blocked"
    assert blocked.exit_code == 5
    assert blocked.payload is not None
    assert blocked.payload["error_code"] == "SMS_APPROVAL_UNAVAILABLE"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
