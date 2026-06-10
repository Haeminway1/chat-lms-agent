from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

from chat_lms_agent.agent_tool_reuse import reuse_check_payload
from chat_lms_agent.side_panel_wordbook import DEFAULT_WORDBOOK_PORT, wordbook_open_plan

WORDBOOK_ROUTE_ID: Final = "lesson_wordbook_status"
FIRST_GATE_TIME_BUDGET_MS: Final = 5000
WORDBOOK_REQUIRED_TOKENS: Final = frozenset(("단어", "단어장", "wordbook", "vocabulary"))
WORDBOOK_WORKFLOW_TOKENS: Final = frozenset(
    (
        "현황",
        "보고",
        "리스트",
        "목록",
        "조회",
        "패널",
        "모르는",
        "html",
        "HTML",
        "수업",
        "학생",
    ),
)
STUDENT_STOPWORDS: Final = frozenset(
    (
        "과외",
        "학생",
        "수업",
        "단어",
        "단어장",
        "현황",
        "보고",
        "리스트",
        "목록",
        "조회",
        "패널",
        "html",
        "HTML",
        "열어줘",
        "보여줘",
        "정리",
        "해줘",
    ),
)


@dataclass(frozen=True, slots=True)
class PromptRoute:
    route_id: str
    student_hint: str | None


def detect_prompt_route(prompt: str) -> PromptRoute | None:
    if not _looks_like_wordbook_request(prompt):
        return None
    return PromptRoute(route_id=WORDBOOK_ROUTE_ID, student_hint=_student_hint(prompt))


def prompt_route_context(route: PromptRoute) -> dict[str, JsonValue]:
    student_argument = (
        route.student_hint if route.student_hint is not None else "<student name from prompt>"
    )
    return {
        "status": "MATCHED",
        "route_id": route.route_id,
        "intent": "learner_wordbook_status_or_list",
        "student_argument": student_argument,
        "first_command": "agent-tools prompt-check --prompt <current prompt> --json",
        "then_command": (
            "side-panel wordbook open-plan "
            f'--student "{student_argument}" --profile-root <root> --json'
        ),
        "fallback_command": "side-panel wordbook ensure-server --profile-root <root> --json",
        "browser_action": (
            "open browser_url with Browser plugin, then summarize existing wordbook data"
        ),
        "legacy_runtime_policy": (
            "lazycodex or legacy scripts may be used only as existing backing runtime; "
            "do not start a new build/scaffold path for wordbook status requests"
        ),
        "must_not": [
            "do not inspect DB schema before the wordbook route",
            "do not create a new HTML report for this request",
            "do not scaffold or build a new wordbook tool",
            "do not search files with rg before the wordbook CLI route",
        ],
        "time_budget_ms": {
            "reuse_check": 5000,
            "open_plan": 10000,
            "browser_open": 15000,
        },
    }


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
            "route_id": WORDBOOK_ROUTE_ID,
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


def prompt_check_payload(
    prompt: str,
    repo_root: Path | None,
    profile: ProfileState | None,
) -> dict[str, JsonValue]:
    route_start = time.perf_counter()
    route = detect_prompt_route(prompt)
    route_elapsed_ms = _elapsed_ms(route_start)

    reuse_start = time.perf_counter()
    reuse = reuse_check_payload(prompt, repo_root, profile)
    reuse_elapsed_ms = _elapsed_ms(reuse_start)

    route_context = prompt_route_context(route) if route is not None else None
    payload: dict[str, JsonValue] = {
        "status": "PASS" if route is not None else "NO_MATCH",
        "schema_version": "prompt-route-check-v1",
        "prompt_redacted": True,
        "decision": _prompt_decision(route, reuse),
        "route": route_context,
        "student_hint": route.student_hint if route is not None else None,
        "reuse_decision": reuse["decision"],
        "matched_tools": _matched_tool_ids(reuse),
        "first_action": (
            "run side-panel wordbook open-plan"
            if route is not None
            else "manual review before custom build"
        ),
        "timings_ms": {
            "route_detection": route_elapsed_ms,
            "reuse_check": reuse_elapsed_ms,
        },
        "acceptance": {
            "route_matched": route is not None,
            "reuse_existing": reuse["decision"] == "reuse_existing",
            "no_build_guard": route_context is not None,
            "first_gate_under_5000_ms": (
                route_elapsed_ms + reuse_elapsed_ms <= FIRST_GATE_TIME_BUDGET_MS
            ),
        },
    }
    if route is not None and profile is not None:
        _attach_wordbook_open_plan(payload, route, profile)
    return payload


def _looks_like_wordbook_request(prompt: str) -> bool:
    normalized = prompt.lower()
    has_wordbook_token = any(token.lower() in normalized for token in WORDBOOK_REQUIRED_TOKENS)
    has_workflow_token = any(token.lower() in normalized for token in WORDBOOK_WORKFLOW_TOKENS)
    return has_wordbook_token and has_workflow_token


def _student_hint(prompt: str) -> str | None:
    for raw_token in prompt.replace(",", " ").replace(":", " ").split():
        token = raw_token.strip()
        if not token or token in STUDENT_STOPWORDS:
            continue
        if any(wordbook_token in token for wordbook_token in WORDBOOK_REQUIRED_TOKENS):
            continue
        return token
    return None


def _attach_wordbook_open_plan(
    payload: dict[str, JsonValue],
    route: PromptRoute,
    profile: ProfileState,
) -> None:
    student = route.student_hint if route.student_hint is not None else "<student>"
    open_plan_start = time.perf_counter()
    code, open_plan = wordbook_open_plan(
        profile,
        student,
        lesson_date=None,
        port=DEFAULT_WORDBOOK_PORT,
    )
    timings = payload.get("timings_ms")
    if isinstance(timings, dict):
        timings["open_plan"] = _elapsed_ms(open_plan_start)
    payload["open_plan_exit_code"] = code
    payload["open_plan"] = open_plan


def _prompt_decision(route: PromptRoute | None, reuse: dict[str, JsonValue]) -> str:
    if route is not None and reuse["decision"] == "reuse_existing":
        return "use_existing_route"
    if route is not None:
        return "route_matched_reuse_review_required"
    return "manual_review_required"


def _matched_tool_ids(reuse: dict[str, JsonValue]) -> list[JsonValue]:
    raw_matches = reuse.get("matches")
    if not isinstance(raw_matches, list):
        return []
    return [
        item["id"]
        for item in raw_matches
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)
