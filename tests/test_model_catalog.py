from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from chat_lms_agent.context import CONTEXT_EVENT_BYTE_CEILING, build_host_context
from chat_lms_agent.model_catalog import (
    CATALOG_SCHEMA_VERSION,
    resolve_role,
    validate_catalog,
)
from chat_lms_agent.state import ProfileState


def test_repo_catalog_resolves_main_model() -> None:
    # Given: the public repo catalog.
    payload = resolve_role(_repo_root(), "main_model")

    # Then: the full provenance chain is returned and the concrete id wins.
    assert payload["status"] == "PASS"
    assert payload["concrete"] == "claude-opus-4-8"
    assert payload["provider"] == "anthropic"
    assert payload["chain"] == ["main_model", "opus", "claude-opus-4-8"]
    assert payload["source"] == "repo"


def test_repo_catalog_file_is_schema_pinned() -> None:
    # Given: the catalog data file.
    raw = json.loads(
        (_repo_root() / "docs" / "model-catalog.json").read_text(encoding="utf-8"),
    )

    # Then: schema version and provider neutrality are pinned.
    assert raw["schema_version"] == CATALOG_SCHEMA_VERSION
    providers = {entry["provider"] for entry in raw["models"].values()}
    assert len(providers) >= 2, "catalog must prove provider neutrality"


def test_unknown_role_is_typed_error() -> None:
    payload = resolve_role(_repo_root(), "nonexistent_role")
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "UNKNOWN_ROLE"


def test_dangling_family_detected_by_validate(tmp_path: Path) -> None:
    # Given: a profile override pointing a role at a missing family.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    override_dir = tmp_path / "profile" / ".chat-lms-state"
    override_dir.mkdir(parents=True)
    (override_dir / "model-catalog.json").write_text(
        json.dumps(
            {
                "schema_version": CATALOG_SCHEMA_VERSION,
                "roles": {"main_model": {"family": "missing-family"}},
            },
        ),
        encoding="utf-8",
    )

    # When: the merged catalog is validated.
    payload = validate_catalog(_repo_root(), profile)

    # Then: the dangling alias is reported, not silently resolved.
    assert payload["status"] == "ERROR"
    problems = json.dumps(payload["problems"])
    assert "DANGLING_FAMILY" in problems
    assert "missing-family" in problems


def test_profile_override_repoints_role(tmp_path: Path) -> None:
    # Given: a profile override re-pointing main_model to the sonnet family.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    override_dir = tmp_path / "profile" / ".chat-lms-state"
    override_dir.mkdir(parents=True)
    (override_dir / "model-catalog.json").write_text(
        json.dumps(
            {
                "schema_version": CATALOG_SCHEMA_VERSION,
                "roles": {"main_model": {"family": "sonnet"}},
            },
        ),
        encoding="utf-8",
    )

    # When: the role resolves with the profile attached.
    payload = resolve_role(_repo_root(), "main_model", profile)

    # Then: the teacher override wins and is labeled as such.
    assert payload["status"] == "PASS"
    assert payload["concrete"] == "claude-sonnet-4-6"
    assert payload["source"] == "profile"


def test_deprecated_concrete_is_rejected(tmp_path: Path) -> None:
    # Given: an override family pointing at a deprecated concrete model.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    override_dir = tmp_path / "profile" / ".chat-lms-state"
    override_dir.mkdir(parents=True)
    (override_dir / "model-catalog.json").write_text(
        json.dumps(
            {
                "schema_version": CATALOG_SCHEMA_VERSION,
                "roles": {"main_model": {"family": "old"}},
                "families": {"old": {"provider": "anthropic", "concrete": "claude-old-1"}},
                "models": {"claude-old-1": {"provider": "anthropic", "status": "deprecated"}},
            },
        ),
        encoding="utf-8",
    )

    # When/Then: resolution refuses deprecated concretes.
    payload = resolve_role(_repo_root(), "main_model", profile)
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "MODEL_DEPRECATED"


def test_cli_resolve_list_and_validate() -> None:
    # Given/When: the harness model CLI verbs run against the repo catalog.
    resolve = _run_cli("harness", "model", "resolve", "--role", "main_model", "--json")
    listing = _run_cli("harness", "model", "list", "--json")
    validate = _run_cli("harness", "model", "validate", "--json")

    # Then: all verbs answer with the catalog contract.
    assert resolve.returncode == 0, resolve.stdout
    resolved = json.loads(resolve.stdout)
    assert resolved["concrete"] == "claude-opus-4-8"
    assert listing.returncode == 0, listing.stdout
    listed = json.loads(listing.stdout)
    assert "main_model" in json.dumps(listed["roles"])
    assert validate.returncode == 0, validate.stdout
    assert json.loads(validate.stdout)["status"] == "PASS"


def test_hydration_includes_model_catalog_section(tmp_path: Path) -> None:
    # Given: a hydration build.
    context = build_host_context(_repo_root(), str(tmp_path / "p"), None)

    # Then: the role staffing chart rides along, still inside the ceiling.
    section = context["model_catalog"]
    assert isinstance(section, dict)
    roles = section["roles"]
    assert isinstance(roles, dict)
    assert roles["main_model"] == "claude-opus-4-8"
    blob = json.dumps(context, ensure_ascii=False, sort_keys=True).encode("utf-8")
    assert len(blob) <= CONTEXT_EVENT_BYTE_CEILING


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
