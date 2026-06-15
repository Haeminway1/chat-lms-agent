from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


def prompt_routing_policy_context() -> dict[str, JsonValue]:
    return {
        "schema_version": "prompt-routing-v1",
        "mandatory_gate": "agent-tools prompt-check --prompt <current prompt> --json",
        "wordbook_requests": {
            "examples": [
                "과외 <학생> 학생 단어 현황 보고",
                "<학생> 단어 리스트 조회",
                "<학생> 모르는 단어 현황",
                "<학생> 단어 HTML 패널 열어줘",
            ],
            "route_id": "lesson_wordbook_status",
            "first_cli": (
                "side-panel wordbook open-plan --student <student> "
                "--profile-root <root> --json"
            ),
            "must_not": [
                "do not create a new report generator",
                "do not inspect DB schema before this route",
                "do not use rg before this route",
            ],
        },
    }
