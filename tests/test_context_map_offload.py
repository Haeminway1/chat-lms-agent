from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_context_map_builds_compact_inventory_without_private_paths(tmp_path: Path) -> None:
    # Given: a private profile with memory and academy DB state.
    _ = _run_cli(
        "memory",
        "upsert",
        "--profile-root",
        str(tmp_path),
        "--key",
        "tool:academy-db",
        "--scope",
        "tool-knowledge",
        "--text",
        f"Use academy DB CLI from {tmp_path}; SECRET_TOKEN=hidden.",
        "--json",
    )
    _ = _run_cli("academy-db", "init", "--profile-root", str(tmp_path), "--json")

    # When: building the compact context map.
    result = _run_cli("context", "map", "build", "--profile-root", str(tmp_path), "--json")

    # Then: the map exposes capabilities without leaking private paths or secrets.
    assert result.returncode == 0, result.stdout
    assert str(tmp_path) not in result.stdout
    assert "SECRET_TOKEN" not in result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "PASS"
    assert payload["schema_version"] == "context-map-v1"
    assert "academy-db" in payload["tool_ids"]
    assert "tool:academy-db" in payload["memory_keys"]
    assert payload["truth_source"] == "generated_from_canonical_sources"


def test_context_offload_put_get_preserves_hash_and_redacts_summary(tmp_path: Path) -> None:
    # Given: a large synthetic output with private-looking material.
    source = tmp_path / "large-output.txt"
    source.write_text(
        (
            "learner row SECRET_TOKEN=hidden teacher password: hunter2 "
            f"api secret = open-sesame {tmp_path}\n"
        )
        * 20,
        encoding="utf-8",
    )

    # When: offloading then retrieving it through the CLI.
    put_result = _run_cli(
        "context",
        "offload",
        "put",
        "--profile-root",
        str(tmp_path),
        "--kind",
        "tool_output",
        "--from",
        str(source),
        "--json",
    )
    put_payload = json.loads(put_result.stdout)
    assert put_payload["original_stored_unredacted"] is True
    assert put_payload["raw_storage"] == (
        "<profile-root>/.chat-lms-state/context-offload/"
        f"{put_payload['offload_id']}.txt"
    )
    get_result = _run_cli(
        "context",
        "offload",
        "get",
        "--profile-root",
        str(tmp_path),
        "--ref",
        put_payload["offload_id"],
        "--json",
    )
    reveal_result = _run_cli(
        "context",
        "offload",
        "get",
        "--profile-root",
        str(tmp_path),
        "--ref",
        put_payload["offload_id"],
        "--reveal",
        "--json",
    )

    # Then: summary and default retrieval are redacted, while explicit reveal returns the original.
    assert put_result.returncode == 0, put_result.stdout
    assert get_result.returncode == 0, get_result.stdout
    assert reveal_result.returncode == 0, reveal_result.stdout
    assert str(tmp_path) not in put_result.stdout
    assert "SECRET_TOKEN" not in put_result.stdout
    assert "hunter2" not in put_result.stdout
    assert "open-sesame" not in put_result.stdout
    assert str(tmp_path) not in get_result.stdout
    assert "SECRET_TOKEN" not in get_result.stdout
    assert "hunter2" not in get_result.stdout
    assert "open-sesame" not in get_result.stdout
    get_payload = json.loads(get_result.stdout)
    reveal_payload = json.loads(reveal_result.stdout)
    assert get_payload["sha256"] == put_payload["sha256"]
    assert get_payload["integrity"] == "PASS"
    assert get_payload["content_redacted"] is True
    assert "SECRET_TOKEN=hidden" not in get_payload["content"]
    assert reveal_payload["content_redacted"] is False
    assert "SECRET_TOKEN=hidden" in reveal_payload["content"]
    assert "hunter2" in reveal_payload["content"]
    assert "open-sesame" in reveal_payload["content"]


def test_context_offload_rejects_non_utf8_source_without_traceback(tmp_path: Path) -> None:
    # Given: a binary file that cannot be decoded as UTF-8 text.
    source = tmp_path / "binary-output.bin"
    source.write_bytes(b"\xff\xfe\xfa")

    # When: the agent tries to offload it as text.
    result = _run_cli(
        "context",
        "offload",
        "put",
        "--profile-root",
        str(tmp_path),
        "--kind",
        "tool_output",
        "--from",
        str(source),
        "--json",
    )

    # Then: the CLI returns a structured encoding error instead of a traceback.
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "INVALID_OFFLOAD_ENCODING"


def test_context_offload_missing_original_is_recoverable_error(tmp_path: Path) -> None:
    # Given: an offloaded artifact whose original file was removed.
    source = tmp_path / "large-output.txt"
    source.write_text("original content", encoding="utf-8")
    put_result = _run_cli(
        "context",
        "offload",
        "put",
        "--profile-root",
        str(tmp_path),
        "--kind",
        "log",
        "--from",
        str(source),
        "--json",
    )
    offload_id = json.loads(put_result.stdout)["offload_id"]
    stored = tmp_path / ".chat-lms-state" / "context-offload" / f"{offload_id}.txt"
    stored.unlink()

    # When: retrieving the missing artifact.
    result = _run_cli(
        "context",
        "offload",
        "get",
        "--profile-root",
        str(tmp_path),
        "--ref",
        offload_id,
        "--json",
    )

    # Then: it fails as a recoverable integrity error.
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "OFFLOAD_ORIGINAL_MISSING"
    assert payload["recoverable"] is True


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
    )
