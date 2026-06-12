from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from chat_lms_agent.cli_io import flag, option, profile_state_or_error, write_json
from chat_lms_agent.kakao_browser_chat import KakaoChatApiError
from chat_lms_agent.kakao_browser_chat_runner import (
    pull_kakao_chat_threads,
    send_kakao_chat_reply,
)
from chat_lms_agent.kakao_calibration import (
    KakaoCalibrationError,
    calibration_error_payload,
    load_calibration_pack,
)
from chat_lms_agent.kakao_core import ingest_chat_history
from chat_lms_agent.kakao_login import (
    KAKAO_PROFILE_DISPLAY,
    KakaoBrowserOptions,
    KakaoLoginRequiredError,
    KakaoPlaywrightMissingError,
    run_kakao_login,
)

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue, ProfileState

KAKAO_SKIP_BROWSER_ENV: Final = "CHAT_LMS_AGENT_KAKAO_SKIP_BROWSER"


@dataclass(frozen=True, slots=True)
class LiveKakaoChatPage:
    args: list[str]
    profile: ProfileState

    def send_chat_reply(self, contact_id: str, text: str) -> None:
        if _live_browser_disabled():
            raise KakaoLoginRequiredError
        admin_url = _admin_url_or_raise(self.args, self.profile)
        _ = send_kakao_chat_reply(
            admin_url=admin_url,
            headed=flag(self.args, "--headed"),
            contact_id=contact_id,
            text=text,
        )


def handle_kakao_login(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    calibration = load_calibration_pack(profile)
    admin_url = option(args, "--admin-url")
    start_url = (
        admin_url
        if admin_url is not None
        else None if isinstance(calibration, KakaoCalibrationError) else calibration.admin_url
    )
    try:
        result = run_kakao_login(
            KakaoBrowserOptions(
                headed=flag(args, "--headed"),
                start_url=start_url,
            ),
        )
    except KakaoPlaywrightMissingError:
        write_json(
            {
                "status": "ERROR",
                "error_code": "KAKAO_EXTRA_NOT_INSTALLED",
                "message": "Install the existing [classcard] Playwright extra and Chromium.",
            },
        )
        return 2
    except KakaoLoginRequiredError:
        write_json(
            {
                "status": "NEEDS_INPUT",
                "error_code": "KAKAO_LOGIN_REQUIRED",
                "message_ko": "열린 브라우저에서 카카오 로그인/2FA를 완료한 뒤 다시 실행하세요.",
                "profile_dir": KAKAO_PROFILE_DISPLAY,
            },
        )
        return 2
    write_json(
        {
            "status": "PASS",
            "login_state": result.status,
            "profile_dir": KAKAO_PROFILE_DISPLAY,
        },
    )
    return 0


def handle_kakao_chats_pull(args: list[str], repo_root: Path) -> int:
    profile = profile_state_or_error(args, repo_root)
    if profile is None:
        return 4
    admin_url = _admin_url_or_payload(args, profile)
    if not isinstance(admin_url, str):
        write_json(admin_url)
        return 2
    if _live_browser_disabled():
        write_json(_login_required_payload())
        return 2
    try:
        pulled = pull_kakao_chat_threads(
            admin_url=admin_url,
            headed=flag(args, "--headed"),
        )
    except (KakaoPlaywrightMissingError, KakaoLoginRequiredError, KakaoChatApiError) as error:
        write_json(live_error_payload(error))
        return 2

    def fetch_media(url: str) -> bytes:
        return pulled.media_by_url[url]

    thread_payloads: list[JsonValue] = []
    for thread in pulled.threads:
        result = ingest_chat_history(
            profile,
            contact_id=thread.contact_id,
            messages=thread.messages,
            media_fetcher=fetch_media if pulled.media_by_url else None,
        )
        thread_payloads.append(
            {
                "contact_id": result.contact_id,
                "chat_id": thread.chat_id,
                "message_count": result.message_count,
                "new_count": result.new_count,
            },
        )
    write_json({"status": "PASS", "threads": thread_payloads})
    return 0


def _admin_url_or_payload(args: list[str], profile: ProfileState) -> str | dict[str, JsonValue]:
    admin_url = option(args, "--admin-url")
    if admin_url is not None:
        return admin_url
    calibration = load_calibration_pack(profile)
    if isinstance(calibration, KakaoCalibrationError):
        return calibration_error_payload(calibration)
    if calibration.admin_url is not None:
        return calibration.admin_url
    return {
        "status": "ERROR",
        "error_code": "KAKAO_PROFILE_ID_MISSING",
        "message": "Run kakao login/calibrate with --admin-url for this channel first.",
    }


def _admin_url_or_raise(args: list[str], profile: ProfileState) -> str:
    admin_url = _admin_url_or_payload(args, profile)
    if isinstance(admin_url, str):
        return admin_url
    error_code = admin_url.get("error_code")
    message = admin_url.get("message") or admin_url.get("message_ko") or "Kakao admin URL missing."
    raise KakaoChatApiError(
        error_code=error_code if isinstance(error_code, str) else "KAKAO_PROFILE_ID_MISSING",
        message=message if isinstance(message, str) else "Kakao admin URL missing.",
    )


def _playwright_missing_payload() -> dict[str, JsonValue]:
    return {
        "status": "ERROR",
        "error_code": "KAKAO_EXTRA_NOT_INSTALLED",
        "message": "Install the existing [classcard] Playwright extra and Chromium.",
    }


def _login_required_payload() -> dict[str, JsonValue]:
    return {
        "status": "ERROR",
        "error_code": "KAKAO_LOGIN_REQUIRED",
        "message_ko": "카카오 채널 관리자센터 로그인/2FA 후 다시 실행하세요.",
        "profile_dir": KAKAO_PROFILE_DISPLAY,
    }


def _chat_api_error_payload(error: KakaoChatApiError) -> dict[str, JsonValue]:
    return {"status": "ERROR", "error_code": error.error_code, "message": error.message}


def live_error_payload(
    error: KakaoPlaywrightMissingError | KakaoLoginRequiredError | KakaoChatApiError,
) -> dict[str, JsonValue]:
    if isinstance(error, KakaoPlaywrightMissingError):
        return _playwright_missing_payload()
    if isinstance(error, KakaoLoginRequiredError):
        return _login_required_payload()
    return _chat_api_error_payload(error)


def _live_browser_disabled() -> bool:
    return os.environ.get(KAKAO_SKIP_BROWSER_ENV) == "1"
