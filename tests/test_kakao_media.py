from __future__ import annotations

from pathlib import Path

from chat_lms_agent.kakao_core import KakaoChatMessage, ingest_chat_history, load_chat_history
from chat_lms_agent.state import ProfileState, resolve_profile_state


def test_inbound_media_urls_are_fetched_to_profile_store(tmp_path: Path) -> None:
    # Given: an inbound synthetic Kakao message with a media URL.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)
    fetched_urls: list[str] = []

    def fetch_media(url: str) -> bytes:
        fetched_urls.append(url)
        return b"synthetic image bytes"

    message = KakaoChatMessage(
        message_id="m-media",
        direction="inbound",
        text="Synthetic image attached",
        sent_at="2026-06-12T09:00:00+09:00",
        media_urls=("https://media.example.test/photo.jpg",),
    )

    # When: history is ingested with a media fetcher.
    result = ingest_chat_history(
        profile,
        contact_id="synthetic-contact",
        messages=(message,),
        media_fetcher=fetch_media,
    )
    loaded = load_chat_history(profile, contact_id="synthetic-contact")

    # Then: the media URL is fetched once and stored under the profile Kakao media dir.
    assert result.new_count == 1
    assert fetched_urls == ["https://media.example.test/photo.jpg"]
    assert len(loaded) == 1
    assert loaded[0].media_urls == ("https://media.example.test/photo.jpg",)
    assert loaded[0].media_refs == (
        "<profile-root>/.chat-lms-state/kakao/media/synthetic-contact/m-media/0.bin",
    )
    media_file = (
        tmp_path
        / ".chat-lms-state"
        / "kakao"
        / "media"
        / "synthetic-contact"
        / "m-media"
        / "0.bin"
    )
    assert media_file.read_bytes() == b"synthetic image bytes"


def test_outbound_media_urls_are_not_fetched_by_inbound_ingest(tmp_path: Path) -> None:
    # Given: an outbound message that contains a URL-shaped media reference.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)

    def fetch_media(_url: str) -> bytes:
        raise AssertionError

    # When: the outbound message is ingested.
    _ = ingest_chat_history(
        profile,
        contact_id="synthetic-contact",
        messages=(
            KakaoChatMessage(
                message_id="out-media",
                direction="outbound",
                text="Synthetic outbound image",
                sent_at="2026-06-12T09:00:00+09:00",
                media_urls=("https://media.example.test/outbound.jpg",),
            ),
        ),
        media_fetcher=fetch_media,
    )
    loaded = load_chat_history(profile, contact_id="synthetic-contact")

    # Then: the original URL is retained but no profile media file is created.
    assert loaded[0].media_urls == ("https://media.example.test/outbound.jpg",)
    assert loaded[0].media_refs == ()
    assert not (tmp_path / ".chat-lms-state" / "kakao" / "media").exists()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
