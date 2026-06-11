from __future__ import annotations

from pathlib import Path

from chat_lms_agent.kakao_calibration import (
    KakaoCalibrationError,
    load_calibration_pack,
)
from chat_lms_agent.state import ProfileState, resolve_profile_state


def test_missing_calibration_pack_returns_typed_error(tmp_path: Path) -> None:
    # Given: a clean profile with no Kakao calibration pack.
    profile = resolve_profile_state(_repo_root(), str(tmp_path), None)
    assert isinstance(profile, ProfileState)

    # When: the pack is loaded.
    result = load_calibration_pack(profile)

    # Then: callers get a typed missing-calibration error, not guessed selectors.
    assert isinstance(result, KakaoCalibrationError)
    assert result.error_code == "KAKAO_CALIBRATION_REQUIRED"
    assert result.pack_path.name == "calibration.json"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
