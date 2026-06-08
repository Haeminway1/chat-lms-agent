from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path


def test_chat_lms_imports() -> None:
    # Given: the public package name and CLI module.
    package_name = "chat_lms_agent"

    # When: the modules are imported by a downstream user.
    package = importlib.import_module(package_name)
    cli = importlib.import_module(f"{package_name}.cli")

    # Then: a version and callable CLI entrypoint are exposed.
    assert isinstance(package.__version__, str)
    assert package.__version__
    assert callable(cli.app)


def test_chat_lms_module_version_command() -> None:
    # Given: a fresh checkout with the source tree on the Python path.
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")

    # When: the package module is invoked with the version flag.
    result = subprocess.run(
        [sys.executable, "-m", "chat_lms_agent", "--version"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        check=False,
        text=True,
    )

    # Then: it exits cleanly and identifies the public tool.
    assert result.returncode == 0, result.stderr
    assert "chat-lms-agent" in result.stdout
