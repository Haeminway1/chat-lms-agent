from __future__ import annotations

import json
from dataclasses import dataclass
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.state import STATE_DIR

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

CALIBRATION_SCHEMA_VERSION: Final = "kakao-calibration-v1"
KAKAO_STATE_DIR: Final = "kakao"
CALIBRATION_FILE: Final = "calibration.json"
REQUIRED_SELECTORS: Final = (
    "message_composer",
    "message_textarea",
    "send_button",
    "chat_list",
    "chat_reply_textarea",
    "chat_reply_button",
)


@dataclass(frozen=True, slots=True)
class KakaoCalibrationError:
    error_code: str
    message: str
    pack_path: Path


@dataclass(frozen=True, slots=True)
class KakaoCalibrationPack:
    captured_at: str
    free_quota_ceiling: int | None
    selectors: dict[str, str]
    pack_path: Path


def calibration_pack_path(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / KAKAO_STATE_DIR / CALIBRATION_FILE


def load_calibration_pack(profile: ProfileState) -> KakaoCalibrationPack | KakaoCalibrationError:
    pack_path = calibration_pack_path(profile)
    if not pack_path.exists():
        return KakaoCalibrationError(
            error_code="KAKAO_CALIBRATION_REQUIRED",
            message="Kakao selector calibration is required before browser automation.",
            pack_path=pack_path,
        )
    try:
        payload = cast("JsonValue", json.loads(pack_path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return KakaoCalibrationError(
            error_code="KAKAO_CALIBRATION_INVALID",
            message="Kakao calibration pack is not valid JSON.",
            pack_path=pack_path,
        )
    if not isinstance(payload, dict):
        return KakaoCalibrationError(
            error_code="KAKAO_CALIBRATION_INVALID",
            message="Kakao calibration pack must be a JSON object.",
            pack_path=pack_path,
        )
    return _parse_pack(payload, pack_path)


def calibration_error_payload(error: KakaoCalibrationError) -> dict[str, JsonValue]:
    return {
        "status": "ERROR",
        "error_code": error.error_code,
        "message": error.message,
        "pack": "<profile-root>/.chat-lms-state/kakao/calibration.json",
    }


def _parse_pack(
    payload: dict[str, JsonValue],
    pack_path: Path,
) -> KakaoCalibrationPack | KakaoCalibrationError:
    if payload.get("schema_version") != CALIBRATION_SCHEMA_VERSION:
        return KakaoCalibrationError(
            error_code="KAKAO_CALIBRATION_INVALID",
            message="Kakao calibration pack schema is unsupported.",
            pack_path=pack_path,
        )
    selectors_raw = payload.get("selectors")
    if not isinstance(selectors_raw, dict):
        return KakaoCalibrationError(
            error_code="KAKAO_SELECTOR_MISSING",
            message="Kakao calibration pack has no selectors object.",
            pack_path=pack_path,
        )
    selectors: dict[str, str] = {}
    for key in REQUIRED_SELECTORS:
        value = selectors_raw.get(key)
        if not isinstance(value, str) or not value.strip():
            return KakaoCalibrationError(
                error_code="KAKAO_SELECTOR_MISSING",
                message=f"Kakao selector missing: {key}",
                pack_path=pack_path,
            )
        selectors[key] = value
    captured_at = payload.get("captured_at")
    quota = payload.get("free_quota_ceiling")
    free_quota_ceiling = quota if isinstance(quota, int) and not isinstance(quota, bool) else None
    return KakaoCalibrationPack(
        captured_at=captured_at if isinstance(captured_at, str) else "",
        free_quota_ceiling=free_quota_ceiling,
        selectors=selectors,
        pack_path=pack_path,
    )
