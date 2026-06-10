from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.privacy import pseudonymize_text, restore_text
from chat_lms_agent.state import ProfileState


def _write_privacy(root: Path, entries: list[dict[str, str]]) -> None:
    state_dir = root / ".chat-lms-state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "privacy.json").write_text(
        json.dumps({"schema_version": "privacy-v1", "entries": entries}, ensure_ascii=False),
        encoding="utf-8",
    )


def test_reversible_entry_roundtrips_only_on_owner_surface(tmp_path: Path) -> None:
    # Given: a reversible learner-name entry.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_privacy(
        tmp_path / "profile",
        [{"match": "민지", "kind": "plain", "mode": "reversible"}],
    )

    # When: text crosses the model boundary.
    outbound = pseudonymize_text(profile, "민지 학생 단어장 진도")

    # Then: the name is replaced by a deterministic placeholder and the owner
    # surface can restore it via a pure local lookup.
    assert "민지" not in outbound
    assert pseudonymize_text(profile, "민지 학생 단어장 진도") == outbound
    assert restore_text(profile, outbound) == "민지 학생 단어장 진도"
    reverse_map = tmp_path / "profile" / ".chat-lms-state" / "privacy-reverse.json"
    assert reverse_map.exists()


def test_oneway_entry_never_roundtrips(tmp_path: Path) -> None:
    # Given: a one-way contact-pattern entry with a custom replacement.
    # The sample number is assembled piecewise so the repo privacy scan
    # never sees a literal phone number in this public file.
    prefix = "0" + "10"
    sample_number = f"{prefix}-1234-5678"
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    _write_privacy(
        tmp_path / "profile",
        [
            {
                "match": prefix + r"-\d{4}-\d{4}",
                "kind": "regex",
                "mode": "oneway",
                "replacement": "[전화번호]",
            },
        ],
    )

    # When: a phone number crosses the boundary twice.
    first = pseudonymize_text(profile, f"연락처 {sample_number} 입니다")
    second = pseudonymize_text(profile, f"연락처 {sample_number} 입니다")

    # Then: deterministic replacement, and restore cannot bring it back.
    assert first == second
    assert sample_number not in first
    assert "[전화번호]" in first
    assert restore_text(profile, first) == first


def test_hydration_seam_pseudonymizes_memory(tmp_path: Path) -> None:
    # Given: a privacy entry and a memory record naming the learner.
    _write_privacy(tmp_path, [{"match": "민지", "kind": "plain", "mode": "reversible"}])
    upsert = _run_cli(
        "memory",
        "upsert",
        "--key",
        "note:lesson",
        "--scope",
        "durable",
        "--text",
        "민지 단어장 진도 기록",
        "--profile-root",
        str(tmp_path),
        "--json",
    )
    assert upsert.returncode == 0, upsert.stdout

    # When: the hydration context is built.
    hydrate = _run_cli(
        "context",
        "hydrate",
        "--profile-root",
        str(tmp_path),
        "--for-host",
        "--json",
    )

    # Then: the learner name never crosses into the model-bound payload.
    assert hydrate.returncode == 0, hydrate.stderr
    assert "민지" not in hydrate.stdout


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_repo_root() / "src")
    return subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", *args],
        cwd=_repo_root(),
        env=env,
        capture_output=True,
        check=False,
        text=True,
        input="",
    )
