from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from chat_lms_agent.kakao_quota import record_kakao_send_usage, summarize_kakao_quota
from chat_lms_agent.state import ProfileState, resolve_profile_state

if TYPE_CHECKING:
    import pytest


def test_monthly_quota_counts_current_month_only(tmp_path: Path) -> None:
    # Given: profile-local Kakao send usage across two months.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    record_kakao_send_usage(
        profile,
        sent_at="2026-05-31T23:59:00+09:00",
        units=9,
        surface="friend_broadcast",
        recipient="friend-group:parents",
    )
    record_kakao_send_usage(
        profile,
        sent_at="2026-06-01T09:00:00+09:00",
        units=2,
        surface="friend_broadcast",
        recipient="friend-group:parents",
    )

    # When: quota is summarized for June against a small calibrated ceiling.
    snapshot = summarize_kakao_quota(
        profile,
        free_quota_ceiling=3,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )

    # Then: only current-month usage counts and the near-limit state is visible.
    assert snapshot.month_to_date_sent == 2
    assert snapshot.free_quota_ceiling == 3
    assert snapshot.quota_remaining == 1
    assert snapshot.quota_state == "warning"


def test_quota_over_limit_is_capped_at_zero_remaining(tmp_path: Path) -> None:
    # Given: profile-local usage beyond the calibrated free ceiling.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    record_kakao_send_usage(
        profile,
        sent_at="2026-06-12T09:00:00+09:00",
        units=4,
        surface="chat_reply",
        recipient="synthetic-contact",
    )

    # When: quota is summarized against a ceiling of three units.
    snapshot = summarize_kakao_quota(
        profile,
        free_quota_ceiling=3,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )

    # Then: over-limit state is explicit and remaining quota never goes negative.
    assert snapshot.month_to_date_sent == 4
    assert snapshot.quota_remaining == 0
    assert snapshot.quota_state == "over_limit"


def test_monthly_quota_uses_korean_month_boundaries_and_ignores_invalid(
    tmp_path: Path,
) -> None:
    # Given: usage records around the KST month boundary and one malformed timestamp.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    record_kakao_send_usage(
        profile,
        sent_at="2026-05-31T15:30:00+00:00",
        units=2,
        surface="friend_broadcast",
        recipient="friend-group:parents",
    )
    record_kakao_send_usage(
        profile,
        sent_at="2026-06-30T15:00:00+00:00",
        units=5,
        surface="friend_broadcast",
        recipient="friend-group:parents",
    )
    record_kakao_send_usage(
        profile,
        sent_at="not-a-timestamp",
        units=7,
        surface="friend_broadcast",
        recipient="friend-group:parents",
    )

    # When: quota is summarized for June in Korea.
    snapshot = summarize_kakao_quota(
        profile,
        free_quota_ceiling=10,
        now=datetime(2026, 6, 12, tzinfo=UTC),
    )

    # Then: only the event that lands inside June KST is counted.
    assert snapshot.period == "2026-06"
    assert snapshot.month_to_date_sent == 2
    assert snapshot.quota_remaining == 8


def test_quota_default_now_can_be_fixed_by_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: June usage and a test-controlled default time in July.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    record_kakao_send_usage(
        profile,
        sent_at="2026-06-12T09:00:00+09:00",
        units=2,
        surface="friend_broadcast",
        recipient="friend-group:parents",
    )
    monkeypatch.setenv("CHAT_LMS_AGENT_KAKAO_NOW", "2026-07-01T00:00:00+09:00")

    # When: quota is summarized without an explicit `now` argument.
    snapshot = summarize_kakao_quota(profile, free_quota_ceiling=10)

    # Then: the environment-controlled July period is used.
    assert snapshot.period == "2026-07"
    assert snapshot.month_to_date_sent == 0


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
