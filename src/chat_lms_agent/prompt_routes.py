from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from chat_lms_agent.agent_tool_reuse import reuse_check_payload
from chat_lms_agent.prompt_route_catalog import (
    ROUTE_CATALOG_BYTE_CEILING as _ROUTE_CATALOG_BYTE_CEILING,
)
from chat_lms_agent.prompt_route_catalog import (
    build_route_catalog,
)
from chat_lms_agent.route_packs import load_route_packs, match_pack_route, pack_route_context
from chat_lms_agent.side_panel_wordbook import DEFAULT_WORDBOOK_PORT, wordbook_open_plan

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

WORDBOOK_ROUTE_ID: Final = "lesson_wordbook_status"
ROUTE_CATALOG_BYTE_CEILING: Final = _ROUTE_CATALOG_BYTE_CEILING
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
        "열어줘",
        "보여줘",
        "정리",
        "해줘",
    ),
)
type ResolvedPromptRouteKind = Literal["builtin", "pack"]


@dataclass(frozen=True, slots=True)
class PromptRoute:
    route_id: str
    student_hint: str | None


@dataclass(frozen=True, slots=True)
class ResolvedPromptRoute:
    kind: ResolvedPromptRouteKind
    route_id: str
    route_context: dict[str, JsonValue]
    student_hint: str | None


def detect_prompt_route(prompt: str) -> PromptRoute | None:
    if not _looks_like_wordbook_request(prompt):
        return None
    return PromptRoute(route_id=WORDBOOK_ROUTE_ID, student_hint=_student_hint(prompt))


def resolve_prompt_route(
    prompt: str,
    repo_root: Path | None,
    profile: ProfileState | None,
) -> ResolvedPromptRoute | None:
    builtin = detect_prompt_route(prompt)
    if builtin is not None:
        return ResolvedPromptRoute(
            kind="builtin",
            route_id=builtin.route_id,
            route_context=prompt_route_context(builtin),
            student_hint=builtin.student_hint,
        )
    if repo_root is None:
        return None
    packs, _warnings = load_route_packs(repo_root, profile)
    pack = match_pack_route(packs, prompt)
    if pack is None:
        return None
    return ResolvedPromptRoute(
        kind="pack",
        route_id=pack.pack_id,
        route_context=pack_route_context(pack),
        student_hint=None,
    )


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


def prompt_check_payload(
    prompt: str,
    repo_root: Path | None,
    profile: ProfileState | None,
) -> dict[str, JsonValue]:
    route_start = time.perf_counter()
    route = resolve_prompt_route(prompt, repo_root, profile)
    route_elapsed_ms = _elapsed_ms(route_start)

    reuse_start = time.perf_counter()
    reuse = reuse_check_payload(prompt, repo_root, profile)
    reuse_elapsed_ms = _elapsed_ms(reuse_start)

    route_context = route.route_context if route is not None else None
    payload: dict[str, JsonValue] = {
        "status": "PASS" if route is not None else "NO_MATCH",
        "schema_version": "prompt-route-check-v1",
        "prompt_redacted": True,
        "decision": _prompt_decision(route, reuse),
        "route": route_context,
        "student_hint": route.student_hint if route is not None else None,
        "reuse_decision": reuse["decision"],
        "matched_tools": _matched_tool_ids(reuse),
        "first_action": _first_action(route),
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
    if route is not None and route.kind == "builtin" and profile is not None:
        _attach_wordbook_open_plan(
            payload,
            PromptRoute(route_id=route.route_id, student_hint=route.student_hint),
            profile,
        )
    if route is None:
        payload["route_catalog"] = build_route_catalog(repo_root, profile)
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


def _first_action(route: ResolvedPromptRoute | None) -> str:
    if route is None:
        return "manual review before custom build"
    if route.kind == "builtin":
        return "run side-panel wordbook open-plan"
    first_command = route.route_context.get("first_command")
    if isinstance(first_command, str) and first_command:
        return f"run {first_command}"
    return "run matched route first_command"


def _prompt_decision(route: ResolvedPromptRoute | None, reuse: dict[str, JsonValue]) -> str:
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
