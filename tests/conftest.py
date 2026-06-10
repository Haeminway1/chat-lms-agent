"""Hermetic test environment.

Every test runs with ambient credentials blanked and the profile-root
environment variable redirected to a per-test temporary directory, so a
developer machine configured for a real private profile can never leak test
writes into real learner data (gap-analysis P0-8).
"""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

_SECRET_ENV_PATTERN = re.compile(r"TOKEN|SECRET|API_?KEY|PASSWORD|CREDENTIAL", re.IGNORECASE)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for key in list(os.environ):
        if _SECRET_ENV_PATTERN.search(key):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CHAT_LMS_AGENT_PROFILE_ROOT", str(tmp_path / "hermetic-profile"))
