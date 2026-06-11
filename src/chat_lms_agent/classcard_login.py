from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ClasscardCredentials:
    username: str
    password: str


def default_credentials_path() -> Path:
    return Path.home() / ".chat_lms_agent" / "classcard_credentials.json"


def save_classcard_credentials(username: str, password: str, path: str | Path | None = None) -> Path:
    target = Path(path) if path else default_credentials_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"username": username, "password": password}, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_classcard_credentials(path: str | Path | None = None) -> ClasscardCredentials | None:
    target = Path(path) if path else default_credentials_path()
    if not target.exists():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if not username or not password:
        return None
    return ClasscardCredentials(username, password)
