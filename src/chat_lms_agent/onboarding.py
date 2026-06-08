from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Literal, TypedDict

if TYPE_CHECKING:
    from pathlib import Path

OnboardingStatus = Literal["READY", "VALIDATION_ERROR"]


@dataclass(frozen=True, slots=True)
class OnboardingResult:
    status: OnboardingStatus
    exit_code: int
    message_ko: str


def validate_answers(path: Path) -> OnboardingResult:
    try:
        json.loads(path.read_text(encoding="utf-8-sig"))
    except (JSONDecodeError, OSError):
        return OnboardingResult(
            status="VALIDATION_ERROR",
            exit_code=2,
            message_ko="onboarding answers must be valid JSON",
        )
    return OnboardingResult(status="READY", exit_code=0, message_ko="onboarding ready")


class OnboardingPayload(TypedDict):
    status: str
    exit_code: int
    message_ko: str


def result_to_jsonable(result: OnboardingResult) -> OnboardingPayload:
    return {
        "status": result.status,
        "exit_code": result.exit_code,
        "message_ko": result.message_ko,
    }
