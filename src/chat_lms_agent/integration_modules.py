"""External Integration Module framework.

Every module that talks to the world outside the teacher's machine is
described on four axes (see ``docs/external-integration-contract.md``)
and, when it can reach another human (``third_party``), must pass the
shared outward-send approval gate below — the exact recipient-bound,
single-use pattern proven by ``gws gmail send``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from chat_lms_agent.approvals import (
    approval_id_for,
    approval_is_approved,
    approval_is_consumed,
    approval_is_denied,
    consume_approval,
    ensure_approval_request,
)

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState


@dataclass(frozen=True, slots=True)
class IntegrationModule:
    module_id: str
    capability_tier: str
    setup_model: str
    outward_writes: tuple[str, ...]
    secret_path: str | None
    approval_required: bool
    status: str


INTEGRATION_MODULES: tuple[IntegrationModule, ...] = (
    IntegrationModule(
        module_id="gws",
        capability_tier="official_api",
        setup_model="embedded_consent",
        outward_writes=("self_account", "third_party"),
        secret_path="~/.chat_lms_agent/google_token.json",
        approval_required=True,
        status="active",
    ),
    IntegrationModule(
        module_id="classcard",
        capability_tier="browser_automation",
        setup_model="per_user_login",
        outward_writes=("self_account",),
        secret_path="~/.chat_lms_agent/classcard_credentials.json",
        approval_required=False,
        status="active",
    ),
    IntegrationModule(
        module_id="sms",
        capability_tier="official_api",
        setup_model="per_user_account",
        outward_writes=("third_party",),
        secret_path="~/.chat_lms_agent/solapi_credentials.json",
        approval_required=True,
        status="planned",
    ),
    IntegrationModule(
        module_id="kakao",
        capability_tier="browser_automation",
        setup_model="per_user_channel",
        outward_writes=("third_party",),
        secret_path="~/.chat_lms_agent/kakao-channel-profile",
        approval_required=True,
        status="planned",
    ),
)


@dataclass(frozen=True, slots=True)
class OutwardGate:
    decision: Literal["proceed", "needs_approval", "blocked"]
    exit_code: int
    payload: dict[str, JsonValue] | None
    plan_id: str
    approval_id: str


def evaluate_outward_send(  # noqa: PLR0913 - explicit gate surface
    profile: ProfileState,
    approval_id: str | None,
    *,
    kind: str,
    recipient: str,
    summary: str,
    error_prefix: str,
) -> OutwardGate:
    """Gate an outward send to a human behind a recipient-bound approval.

    The plan id binds the approval to this exact recipient and summary:
    approving one send never authorizes a different one.
    """
    plan_id = f"{kind}:{recipient}:{summary}"
    operation = f"{kind} to {recipient}: {summary}"
    plan_approval_id = approval_id_for(plan_id)
    if approval_is_denied(profile, plan_approval_id, plan_id) or approval_is_consumed(
        profile,
        plan_approval_id,
        plan_id,
    ):
        return OutwardGate(
            decision="blocked",
            exit_code=5,
            payload={
                "status": "BLOCKED",
                "error_code": f"{error_prefix}_APPROVAL_UNAVAILABLE",
                "approval_id": plan_approval_id,
                "message_ko": "이 발송 건의 승인이 거부되었거나 이미 사용되었습니다.",
            },
            plan_id=plan_id,
            approval_id=plan_approval_id,
        )
    if approval_id is None or not approval_is_approved(profile, approval_id, plan_id):
        request = ensure_approval_request(profile, plan_id=plan_id, operation=operation)
        return OutwardGate(
            decision="needs_approval",
            exit_code=3,
            payload={
                "status": "NEEDS_APPROVAL",
                "approval_id": request.get("approval_id"),
                "operation": operation,
                "message_ko": (
                    "발송은 교사 승인이 필요합니다. approve 후 --approval-id 로 "
                    "다시 실행하세요."
                ),
            },
            plan_id=plan_id,
            approval_id=str(request.get("approval_id")),
        )
    return OutwardGate(
        decision="proceed",
        exit_code=0,
        payload=None,
        plan_id=plan_id,
        approval_id=approval_id,
    )


def consume_outward_send(profile: ProfileState, gate: OutwardGate) -> None:
    consume_approval(profile, gate.approval_id, gate.plan_id)
