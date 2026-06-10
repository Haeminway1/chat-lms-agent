"""Zero-content usage telemetry: surface ids, counts, timestamps only.

Structural reference: roach-pi workspace-memory usage scoring and the
hermes curator trait — usage signals feed promotion *suggestions*; nothing
is ever auto-promoted or auto-deleted, and no learner data or prompt text
is recorded.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

from chat_lms_agent.state import read_state_mapping, write_state_mapping

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue, ProfileState

USAGE_TELEMETRY_FILE: Final = "usage-telemetry.json"
PROMOTION_NUDGE_THRESHOLD: Final = 3


def record_surface_use(profile: ProfileState, surface_id: str) -> int:
    counts = read_state_mapping(profile, USAGE_TELEMETRY_FILE)
    entry = counts.get(surface_id)
    count = 1
    if isinstance(entry, dict):
        previous = entry.get("count")
        if isinstance(previous, int) and not isinstance(previous, bool):
            count = previous + 1
    counts[surface_id] = {"count": count, "last_used_at": time.time()}
    write_state_mapping(profile, USAGE_TELEMETRY_FILE, counts)
    return count


def usage_counts(profile: ProfileState) -> dict[str, JsonValue]:
    return read_state_mapping(profile, USAGE_TELEMETRY_FILE)


def surface_count(profile: ProfileState, surface_id: str) -> int:
    entry = usage_counts(profile).get(surface_id)
    if isinstance(entry, dict):
        count = entry.get("count")
        if isinstance(count, int) and not isinstance(count, bool):
            return count
    return 0
