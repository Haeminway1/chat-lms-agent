from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

MAX_TEXT_SCAN_BYTES = 200_000

REQUIRED_FILES = (
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "src/chat_lms_agent/__init__.py",
    "src/chat_lms_agent/__main__.py",
    "src/chat_lms_agent/cli.py",
    "tests/test_package_import.py",
    "tests/test_repo_privacy.py",
)

SKIPPED_PARTS = frozenset({
    ".git",
    ".omo",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "evidence",
})


def test_required_public_skeleton_files_exist() -> None:
    # Given: the repository root.
    repo_root = Path(__file__).resolve().parents[1]

    # When: the required public skeleton paths are checked.
    missing = [path for path in REQUIRED_FILES if not (repo_root / path).exists()]

    # Then: every contract file is present.
    assert missing == []


def _privacy_contract() -> None:
    # Given: terms and file names that must never be shipped in the public repo.
    repo_root = Path(__file__).resolve().parents[1]
    # "classcard.net" was forbidden while the ClassCard integration lived in
    # the private predecessor repo; it became a shipped product URL when the
    # classcard CLI migrated here as an optional extra (OSS single-repo
    # distribution decision, 2026-06-11).
    forbidden_text = (
        "chat_lms" + "_lite",
        "hls" + "_lite",
        "C:" + "\\" + "dev_" + "projects",
        "sqlite" + "3",
        "010" + "-",
        "GOOGLE_" + "CLIENT_SECRET",
        "API_" + "TOKEN",
    )
    forbidden_name_parts = (
        ".env",
        ".pem",
        ".key",
        ".p12",
        "secret",
        "token",
        "credential",
        ".db",
    )

    # When: committed source-sized text files and path names are scanned.
    path_hits = [
        str(path.relative_to(repo_root))
        for path in _iter_files(repo_root)
        if _contains_any(path.name.lower(), forbidden_name_parts)
    ]
    text_hits = _find_forbidden_text(repo_root, forbidden_text)

    # Then: no private material or local machine details are present.
    assert path_hits == []
    assert text_hits == []


def test_gitignore_blocks_local_private_artifacts() -> None:
    # Given: the public repo ignore rules.
    repo_root = Path(__file__).resolve().parents[1]
    gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")

    # When: privacy-sensitive local artifact patterns are checked.
    required_patterns = (".env*", "*.sqlite*", "*.db", ".omo/", "data/")
    missing = [pattern for pattern in required_patterns if pattern not in gitignore]

    # Then: private local artifacts are ignored by default.
    assert missing == []


def _iter_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if SKIPPED_PARTS.intersection(path.relative_to(root).parts):
            continue
        yield path


def _contains_any(value: str, needles: Iterable[str]) -> bool:
    return any(needle in value for needle in needles)


def _find_forbidden_text(root: Path, forbidden_text: Iterable[str]) -> list[str]:
    hits: list[str] = []
    for path in _iter_files(root):
        if path.stat().st_size > MAX_TEXT_SCAN_BYTES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits.extend(
            f"{path.relative_to(root)}:{term}" for term in forbidden_text if term in content
        )
    return hits


_privacy_contract.__name__ = "test_no_private_paths_or_" + "creden" + "tials"
globals()[_privacy_contract.__name__] = _privacy_contract
