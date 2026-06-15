from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from chat_lms_agent.shortcut_handlers import handle_shortcut
from chat_lms_agent.shortcuts import CommandResult, load_shortcuts
from chat_lms_agent.state import ProfileState


@dataclass(frozen=True, slots=True)
class FakeRunner:
    result: CommandResult
    calls: list[str] = field(default_factory=list)

    def __call__(self, command: str) -> CommandResult:
        """Record a shortcut command instead of executing it."""
        self.calls.append(command)
        return self.result


@dataclass(frozen=True, slots=True)
class FakeBrowser:
    calls: list[str] = field(default_factory=list)

    def __call__(self, url: str) -> bool:
        """Record a URL instead of opening a browser."""
        self.calls.append(url)
        return True


def test_load_shortcuts_skips_malformed_files(tmp_path: Path) -> None:
    # Given: one valid shortcut and several malformed profile shortcut files.
    profile = ProfileState(root=tmp_path / "profile", repo_root=_repo_root())
    shortcuts_dir = profile.root / ".chat-lms-state" / "shortcuts"
    shortcuts_dir.mkdir(parents=True)
    _write_shortcut(
        shortcuts_dir / "daily.json",
        {
            "schema_version": "shortcut-v1",
            "name": "daily",
            "description": "Open daily report",
            "run": "chat-lms-agent academy-db report build --report daily --json",
            "open_browser": True,
        },
    )
    (shortcuts_dir / "broken.json").write_text("{not json", encoding="utf-8")
    _write_shortcut(shortcuts_dir / "empty-name.json", {"schema_version": "shortcut-v1"})
    _write_shortcut(
        shortcuts_dir / "bad-browser.json",
        {
            "schema_version": "shortcut-v1",
            "name": "bad-browser",
            "run": "echo ok",
            "open_browser": "yes",
        },
    )

    # When: shortcuts load from the profile state directory.
    shortcuts, warnings = load_shortcuts(profile)

    # Then: valid shortcuts survive and invalid files warn without aborting.
    assert [shortcut.name for shortcut in shortcuts] == ["daily"]
    assert shortcuts[0].open_browser is True
    assert len(warnings) == 3


def test_shortcut_add_list_run_and_remove_with_fakes(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    # Given: a profile-root and fake side-effect adapters.
    runner = FakeRunner(
        CommandResult(exit_code=0, stdout="\nhttps://local/report.html\n", stderr=""),
    )
    browser = FakeBrowser()

    # When: a shortcut is added, listed, run, and removed.
    add_exit = handle_shortcut(
        [
            "shortcut",
            "add",
            "--profile-root",
            str(tmp_path),
            "--name",
            "daily",
            "--run",
            "echo https://local/report.html",
            "--description",
            "Daily report",
            "--open-browser",
            "--json",
        ],
        _repo_root(),
        command_runner=runner,
        browser_opener=browser,
    )
    list_exit = handle_shortcut(
        ["shortcut", "list", "--profile-root", str(tmp_path), "--json"],
        _repo_root(),
        command_runner=runner,
        browser_opener=browser,
    )
    run_exit = handle_shortcut(
        ["shortcut", "run", "--profile-root", str(tmp_path), "--name", "daily", "--json"],
        _repo_root(),
        command_runner=runner,
        browser_opener=browser,
    )
    remove_exit = handle_shortcut(
        ["shortcut", "remove", "--profile-root", str(tmp_path), "--name", "daily", "--json"],
        _repo_root(),
        command_runner=runner,
        browser_opener=browser,
    )

    # Then: the command and browser are invoked through fakes only.
    stdout_lines = capsys.readouterr().out.splitlines()
    assert [add_exit, list_exit, run_exit, remove_exit] == [0, 0, 0, 0]
    list_payload = json.loads(stdout_lines[1])
    assert list_payload["shortcuts"][0]["name"] == "daily"
    run_payload = json.loads(stdout_lines[2])
    assert run_payload["status"] == "PASS"
    assert run_payload["url"] == "https://local/report.html"
    assert run_payload["exit_code"] == 0
    assert run_payload["stdout_tail"] == "https://local/report.html"
    assert runner.calls == ["echo https://local/report.html"]
    assert browser.calls == ["https://local/report.html"]
    assert not (tmp_path / ".chat-lms-state" / "shortcuts" / "daily.json").exists()


def test_shortcut_run_unknown_name_returns_typed_error(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    # Given: an empty shortcut registry.
    runner = FakeRunner(CommandResult(exit_code=0, stdout="unused", stderr=""))

    # When: a missing shortcut is run.
    exit_code = handle_shortcut(
        ["shortcut", "run", "--profile-root", str(tmp_path), "--name", "missing", "--json"],
        _repo_root(),
        command_runner=runner,
        browser_opener=FakeBrowser(),
    )

    # Then: no command runs and the error is typed.
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "UNKNOWN_SHORTCUT"
    assert runner.calls == []


def test_shortcut_cli_add_list_and_remove_dispatch(tmp_path: Path) -> None:
    # Given/When: the public CLI command writes and lists a shortcut.
    add_result = _run_cli(
        "shortcut",
        "add",
        "--profile-root",
        str(tmp_path),
        "--name",
        "daily",
        "--run",
        "echo https://local/report.html",
        "--json",
    )
    list_result = _run_cli("shortcut", "list", "--profile-root", str(tmp_path), "--json")
    remove_result = _run_cli(
        "shortcut",
        "remove",
        "--profile-root",
        str(tmp_path),
        "--name",
        "daily",
        "--json",
    )

    # Then: parser and top-level dispatch reach the shortcut handler.
    assert [add_result.returncode, list_result.returncode, remove_result.returncode] == [0, 0, 0]
    list_payload = json.loads(list_result.stdout)
    assert list_payload["status"] == "PASS"
    assert list_payload["shortcuts"][0]["name"] == "daily"


def test_shortcut_add_rejects_empty_name_and_run(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    # Given/When: add receives empty values from the CLI boundary.
    empty_name_exit = handle_shortcut(
        [
            "shortcut",
            "add",
            "--profile-root",
            str(tmp_path),
            "--name",
            " ",
            "--run",
            "",
            "--json",
        ],
        _repo_root(),
        command_runner=FakeRunner(CommandResult(exit_code=0, stdout="", stderr="")),
        browser_opener=FakeBrowser(),
    )
    empty_name_payload = json.loads(capsys.readouterr().out)
    empty_run_exit = handle_shortcut(
        [
            "shortcut",
            "add",
            "--profile-root",
            str(tmp_path),
            "--name",
            "daily",
            "--run",
            "",
            "--json",
        ],
        _repo_root(),
        command_runner=FakeRunner(CommandResult(exit_code=0, stdout="", stderr="")),
        browser_opener=FakeBrowser(),
    )
    empty_run_payload = json.loads(capsys.readouterr().out)

    # Then: both operations fail with typed shortcut validation errors.
    assert empty_name_exit == 2
    assert empty_name_payload["status"] == "ERROR"
    assert empty_name_payload["error_code"] == "EMPTY_SHORTCUT_NAME"
    assert empty_run_exit == 2
    assert empty_run_payload["status"] == "ERROR"
    assert empty_run_payload["error_code"] == "EMPTY_SHORTCUT_RUN"


def test_shortcut_add_rejects_path_traversal_name(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    # Given/When: add receives a name that would escape the shortcuts directory.
    exit_code = handle_shortcut(
        [
            "shortcut",
            "add",
            "--profile-root",
            str(tmp_path),
            "--name",
            "../escape",
            "--run",
            "echo https://local/report.html",
            "--json",
        ],
        _repo_root(),
        command_runner=FakeRunner(CommandResult(exit_code=0, stdout="", stderr="")),
        browser_opener=FakeBrowser(),
    )

    # Then: the write is rejected with a typed error.
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "INVALID_SHORTCUT_NAME"
    assert not (tmp_path / ".chat-lms-state" / "escape.json").exists()


def test_shortcut_remove_rejects_path_traversal_name(tmp_path: Path, capsys) -> None:  # noqa: ANN001
    # Given/When: remove receives a name that would escape the shortcuts directory.
    exit_code = handle_shortcut(
        [
            "shortcut",
            "remove",
            "--profile-root",
            str(tmp_path),
            "--name",
            "../escape",
            "--json",
        ],
        _repo_root(),
        command_runner=FakeRunner(CommandResult(exit_code=0, stdout="", stderr="")),
        browser_opener=FakeBrowser(),
    )

    # Then: no profile file outside the shortcuts directory is touched.
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "ERROR"
    assert payload["error_code"] == "UNKNOWN_SHORTCUT"
    assert not (tmp_path / ".chat-lms-state" / "escape.json").exists()


def _write_shortcut(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


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
