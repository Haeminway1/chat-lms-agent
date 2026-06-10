from __future__ import annotations

import os
from pathlib import Path

_SENTINEL_PROFILE = str(Path(__file__).resolve().parent / "_hermeticity-sentinel")
os.environ["CHAT_LMS_AGENT_PROFILE_ROOT"] = _SENTINEL_PROFILE
os.environ["CHAT_LMS_FAKE_SECRET_TOKEN"] = "leak-me"


def test_profile_env_is_isolated() -> None:
    value = os.environ.get("CHAT_LMS_AGENT_PROFILE_ROOT")
    assert value != _SENTINEL_PROFILE
    assert value is not None
    assert value.endswith("hermetic-profile")


def test_secret_env_blanked() -> None:
    assert "CHAT_LMS_FAKE_SECRET_TOKEN" not in os.environ
