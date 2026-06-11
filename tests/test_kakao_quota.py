from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from chat_lms_agent.kakao_quota import record_kakao_send_usage, summarize_kakao_quota
from chat_lms_agent.state import ProfileState, resolve_profile_state


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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
