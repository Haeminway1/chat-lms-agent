from __future__ import annotations

from chat_lms_agent.classcard_direct_audio import ClasscardCard, card_mismatches


def test_card_mismatches_accepts_generated_audio_when_expected_audio_unknown() -> None:
    expected = (ClasscardCard("tell (the difference)", "(차이를) 인지하다, 알다", ""),)
    actual = (
        ClasscardCard(
            "tell (the difference)",
            "(차이를) 인지하다, 알다",
            "/uploads2/audio/u/az/en/20260614/generated.mp3",
        ),
    )

    assert card_mismatches(expected, actual) == ()


def test_card_mismatches_reports_audio_mismatch_when_expected_audio_known() -> None:
    expected = (ClasscardCard("temper", "(명) 화, 기분", "/uploads2/audio/u/az/en/expected.mp3"),)
    actual = (ClasscardCard("temper", "(명) 화, 기분", "/uploads2/audio/u/az/en/actual.mp3"),)

    mismatches = card_mismatches(expected, actual)

    assert len(mismatches) == 1
    assert mismatches[0].fields == ("audio_path",)
