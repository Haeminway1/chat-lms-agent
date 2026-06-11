from __future__ import annotations

import pytest

from chat_lms_agent.kakao_plan import KakaoPlanError, build_send_plan


def test_build_send_plan_splits_400_character_messages_and_caps_run() -> None:
    # Given: a Kakao friend broadcast body longer than two basic-text parts.
    message = "x" * 850

    # When: a run cap allows only two parts this time.
    plan = build_send_plan(
        recipient="friend-group:parents",
        message=message,
        max_parts_per_run=2,
    )

    # Then: the plan keeps 400-character chunks and reports the cap.
    assert [len(part.text) for part in plan.parts] == [400, 400]
    assert [part.index for part in plan.parts] == [0, 1]
    assert plan.total_parts == 3
    assert plan.capped is True
    assert plan.recipient == "friend-group:parents"


def test_build_send_plan_rejects_empty_message() -> None:
    # Given: a blank outbound message.
    # When/Then: planning rejects it with a typed Kakao error.
    with pytest.raises(KakaoPlanError) as raised:
        build_send_plan(
            recipient="friend-group:parents",
            message=" \n\t ",
            max_parts_per_run=10,
        )

    assert raised.value.error_code == "KAKAO_EMPTY_MESSAGE"
