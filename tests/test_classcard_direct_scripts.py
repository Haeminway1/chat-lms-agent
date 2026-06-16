from __future__ import annotations

from chat_lms_agent.classcard_direct_scripts import (
    DIRECT_UPLOAD_SCRIPT,
    READ_CLASS_SETS_SCRIPT,
    SUGGEST_AUDIO_SCRIPT,
)


def test_direct_upload_scripts_allow_blank_audio_path_from_suggest() -> None:
    scripts = (SUGGEST_AUDIO_SCRIPT, DIRECT_UPLOAD_SCRIPT)

    for script in scripts:
        assert "!response.msg || !response.msg.audio_path" not in script
    assert "audio_path: String(response.msg.audio_path || '')" in SUGGEST_AUDIO_SCRIPT
    assert (
        "return {ok: true, audio_path: String(response.msg.audio_path || '')};"
        in DIRECT_UPLOAD_SCRIPT
    )


def test_read_class_sets_script_prefers_set_item_data_idx_for_existing_sets() -> None:
    assert "[data-idx][data-cnt]" in READ_CLASS_SETS_SCRIPT
    assert "dataset.idx" in READ_CLASS_SETS_SCRIPT
    assert "dataset.cnt" in READ_CLASS_SETS_SCRIPT
