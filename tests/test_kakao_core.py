from __future__ import annotations

from pathlib import Path

from chat_lms_agent.kakao_core import (
    KakaoChatMessage,
    ingest_chat_history,
    load_chat_history,
    summarize_chat_history,
)
from chat_lms_agent.kakao_summary import KakaoGeneratedSummary, store_generated_chat_summary
from chat_lms_agent.state import ProfileState, resolve_profile_state


def test_ingest_history_summary_round_trip_synthetic_chat(tmp_path: Path) -> None:
    # Given: synthetic Kakao 1:1 chat messages for a non-real contact.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    messages = (
        KakaoChatMessage(
            message_id="m1",
            direction="inbound",
            text="Synthetic question",
            sent_at="2026-06-11T09:00:00+09:00",
        ),
        KakaoChatMessage(
            message_id="m2",
            direction="outbound",
            text="Synthetic answer",
            sent_at="2026-06-11T09:01:00+09:00",
        ),
        KakaoChatMessage(
            message_id="m3",
            direction="inbound",
            text="Synthetic thanks",
            sent_at="2026-06-11T09:02:00+09:00",
        ),
    )

    # When: the history is ingested and summarized from profile-local state.
    ingest = ingest_chat_history(profile, contact_id="synthetic-contact", messages=messages)
    loaded = load_chat_history(profile, contact_id="synthetic-contact")
    summary = summarize_chat_history(profile, contact_id="synthetic-contact")

    # Then: the round trip preserves messages and produces a useful summary.
    assert ingest.message_count == 3
    assert loaded == messages
    assert summary.contact_id == "synthetic-contact"
    assert summary.inbound_count == 2
    assert summary.outbound_count == 1
    assert summary.last_message_text == "Synthetic thanks"


def test_generated_rolling_summary_is_stored_and_returned(tmp_path: Path) -> None:
    # Given: synthetic messages and a host/model generated rolling summary.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    messages = (
        KakaoChatMessage(
            message_id="m1",
            direction="inbound",
            text="Synthetic concern about homework",
            sent_at="2026-06-12T09:00:00+09:00",
        ),
        KakaoChatMessage(
            message_id="m2",
            direction="outbound",
            text="Synthetic reassurance",
            sent_at="2026-06-12T09:01:00+09:00",
        ),
    )
    _ = ingest_chat_history(profile, contact_id="synthetic-contact", messages=messages)

    # When: the generated summary is stored and the contact is summarized.
    store_generated_chat_summary(
        profile,
        summary=KakaoGeneratedSummary(
            contact_id="synthetic-contact",
            summary_text="Homework concern resolved; parent expects next worksheet.",
            generated_at="2026-06-12T09:02:00+09:00",
            model_id="host-model:test",
            through_message_id="m2",
        ),
    )
    summary = summarize_chat_history(profile, contact_id="synthetic-contact")

    # Then: counts remain available and the stored generated summary wins.
    assert summary.message_count == 2
    assert summary.summary_text == "Homework concern resolved; parent expects next worksheet."
    assert summary.summary_source == "generated"
    assert summary.summary_model_id == "host-model:test"


def test_summary_falls_back_to_counts_when_no_generated_summary(tmp_path: Path) -> None:
    # Given: a chat without any host/model generated summary.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    _ = ingest_chat_history(
        profile,
        contact_id="synthetic-contact",
        messages=(
            KakaoChatMessage(
                message_id="m1",
                direction="inbound",
                text="Synthetic fallback text",
                sent_at="2026-06-12T09:00:00+09:00",
            ),
        ),
    )

    # When: the contact summary is loaded.
    summary = summarize_chat_history(profile, contact_id="synthetic-contact")

    # Then: deterministic fallback text is present without claiming model generation.
    assert summary.summary_source == "fallback"
    assert "1 messages" in summary.summary_text
    assert "Synthetic fallback text" in summary.summary_text


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
