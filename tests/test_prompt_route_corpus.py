from __future__ import annotations

from pathlib import Path

import pytest

from chat_lms_agent import prompt_routes
from chat_lms_agent.state import ProfileState


@pytest.mark.parametrize(
    ("prompt", "expected_route_id"),
    [
        ("학원 수업 뷰어 열어줘", "lesson_assistant_panel"),
        ("수업준비 해줘", "lesson_assistant_panel"),
        ("수업 보조패널 열어줘", "lesson_assistant_panel"),
        ("오늘 수업 패널 띄워줘", "lesson_assistant_panel"),
        ("lesson prep panel for tomorrow", "lesson_assistant_panel"),
        ("가상학생 단어 html 패널 열어줘", "lesson_wordbook_status"),
        ("과외 가상학생 학생 단어 현황 보고", "lesson_wordbook_status"),
        ("카카오 채널로 공지 보내줘", "kakao_channel"),
        ("고마워", None),
    ],
)
def test_prompt_route_corpus_matches_hook_and_prompt_check(
    tmp_path: Path,
    prompt: str,
    expected_route_id: str | None,
) -> None:
    # Given: a fresh profile with only repo-shipped route packs available.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())

    # When: the hook-equivalent resolver and prompt-check process the phrase.
    resolved = prompt_routes.resolve_prompt_route(prompt, _repo_root(), profile)
    payload = prompt_routes.prompt_check_payload(prompt, _repo_root(), profile)

    # Then: both engines agree on the route id for every corpus phrase.
    if expected_route_id is None:
        assert resolved is None
        assert payload["status"] == "NO_MATCH"
        assert payload["route"] is None
        return

    assert resolved is not None
    assert resolved.route_id == expected_route_id
    route = payload["route"]
    assert isinstance(route, dict)
    assert route["route_id"] == expected_route_id
    assert payload["status"] == "PASS"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
