from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from json import JSONDecodeError
from typing import TYPE_CHECKING, Final, Literal, cast

from chat_lms_agent.state import STATE_DIR, JsonValue, redact_text

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import ProfileState

KakaoQuotaState = Literal["unknown", "ok", "warning", "over_limit"]
KAKAO_NOW_ENV: Final = "CHAT_LMS_AGENT_KAKAO_NOW"
KOREA_TZ: Final = timezone(timedelta(hours=9))


@dataclass(frozen=True, slots=True)
class KakaoSendUsageEvent:
    sent_at: str
    units: int
    surface: str
    recipient: str


@dataclass(frozen=True, slots=True)
class KakaoQuotaSnapshot:
    month_to_date_sent: int
    free_quota_ceiling: int | None
    quota_remaining: int | None
    quota_state: KakaoQuotaState
    period: str


def record_kakao_send_usage(
    profile: ProfileState,
    *,
    sent_at: str,
    units: int,
    surface: str,
    recipient: str,
) -> None:
    if units <= 0:
        return
    events = [*_read_events(profile)]
    events.append(
        KakaoSendUsageEvent(
            sent_at=sent_at,
            units=units,
            surface=surface,
            recipient=redact_text(recipient),
        ),
    )
    _write_events(profile, tuple(events))


def summarize_kakao_quota(
    profile: ProfileState,
    *,
    free_quota_ceiling: int | None,
    now: datetime | None = None,
) -> KakaoQuotaSnapshot:
    current = now if now is not None else _current_time()
    period = _period_for_time(current)
    sent = sum(
        event.units for event in _read_events(profile) if _event_period(event.sent_at) == period
    )
    if free_quota_ceiling is None or free_quota_ceiling <= 0:
        return KakaoQuotaSnapshot(
            month_to_date_sent=sent,
            free_quota_ceiling=None,
            quota_remaining=None,
            quota_state="unknown",
            period=period,
        )
    remaining = max(free_quota_ceiling - sent, 0)
    return KakaoQuotaSnapshot(
        month_to_date_sent=sent,
        free_quota_ceiling=free_quota_ceiling,
        quota_remaining=remaining,
        quota_state=_quota_state(sent, free_quota_ceiling),
        period=period,
    )


def _quota_state(sent: int, ceiling: int) -> KakaoQuotaState:
    if sent > ceiling:
        return "over_limit"
    if sent * 3 >= ceiling * 2:
        return "warning"
    return "ok"


def _current_time() -> datetime:
    configured = os.environ.get(KAKAO_NOW_ENV)
    if configured:
        parsed = _parse_datetime(configured)
        if parsed is not None:
            return parsed
    return datetime.now(KOREA_TZ)


def _event_period(sent_at: str) -> str | None:
    parsed = _parse_datetime(sent_at)
    if parsed is None:
        return None
    return _period_for_time(parsed)


def _period_for_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=KOREA_TZ)
    return value.astimezone(KOREA_TZ).strftime("%Y-%m")


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=KOREA_TZ)
    return parsed


def _usage_path(profile: ProfileState) -> Path:
    return profile.root / STATE_DIR / "kakao" / "quota.json"


def _read_events(profile: ProfileState) -> tuple[KakaoSendUsageEvent, ...]:
    path = _usage_path(profile)
    if not path.exists():
        return ()
    try:
        payload = cast("JsonValue", json.loads(path.read_text(encoding="utf-8-sig")))
    except (JSONDecodeError, OSError):
        return ()
    if not isinstance(payload, dict):
        return ()
    raw_events = payload.get("events")
    if not isinstance(raw_events, list):
        return ()
    events: list[KakaoSendUsageEvent] = []
    for item in raw_events:
        if not isinstance(item, dict):
            continue
        parsed = _event_from_json(item)
        if parsed is not None:
            events.append(parsed)
    return tuple(events)


def _write_events(profile: ProfileState, events: tuple[KakaoSendUsageEvent, ...]) -> None:
    path = _usage_path(profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, JsonValue] = {"events": [_event_to_json(event) for event in events]}
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    _ = tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _ = tmp_path.replace(path)


def _event_to_json(event: KakaoSendUsageEvent) -> dict[str, JsonValue]:
    return {
        "sent_at": event.sent_at,
        "units": event.units,
        "surface": event.surface,
        "recipient": event.recipient,
    }


def _event_from_json(payload: dict[str, JsonValue]) -> KakaoSendUsageEvent | None:
    sent_at = payload.get("sent_at")
    units = payload.get("units")
    surface = payload.get("surface")
    recipient = payload.get("recipient")
    if not (
        isinstance(sent_at, str)
        and isinstance(units, int)
        and not isinstance(units, bool)
        and isinstance(surface, str)
        and isinstance(recipient, str)
    ):
        return None
    return KakaoSendUsageEvent(
        sent_at=sent_at,
        units=units,
        surface=surface,
        recipient=recipient,
    )
