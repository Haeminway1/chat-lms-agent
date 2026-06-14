from __future__ import annotations

import json
from pathlib import Path

import pytest

from chat_lms_agent.prompt_routes import prompt_check_payload, resolve_prompt_route
from chat_lms_agent.side_panel_handlers import handle_side_panel

_REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("민준이 출결 보여줘", "learner_records"),
        ("가상학생 출석부 보여줘", "learner_records"),
        ("가상학생 최근 기록 보여줘", "learner_records"),
        ("attendance for 가상학생", "learner_records"),
        ("수업준비 해줘", "lesson_assistant_panel"),
        ("고마워", None),
    ],
)
def test_records_route_resolves_on_shared_engine(prompt: str, expected: str | None) -> None:
    route = resolve_prompt_route(prompt, _REPO, None)
    assert (route.route_id if route is not None else None) == expected


def test_records_route_on_prompt_check() -> None:
    payload = prompt_check_payload("민준이 출결 보여줘", _REPO, None)
    assert payload["status"] == "PASS"
    route = payload["route"]
    assert isinstance(route, dict)
    assert route["route_id"] == "learner_records"


def test_records_open_plan_assetless_is_blocked(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = handle_side_panel(
        [
            "side-panel",
            "records",
            "open-plan",
            "--student",
            "가상민준",
            "--type",
            "attendance",
            "--profile-root",
            str(tmp_path),
            "--json",
        ],
        _REPO,
    )
    out = json.loads(capsys.readouterr().out)
    assert code == 4
    assert out["error_code"] == "LESSON_RUNTIME_MISSING"
