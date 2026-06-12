from __future__ import annotations

import errno
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from http.client import HTTPConnection, HTTPException
from typing import TYPE_CHECKING, Final, Literal, assert_never

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from chat_lms_agent.state import JsonValue

SERVER_HEALTHCHECK_TIMEOUT_SECONDS: Final = 6.0
SERVER_START_WAIT_SECONDS: Final = 12.0
SERVER_START_POLL_SECONDS: Final = 0.2

ServerStatus = Literal["running", "not_running", "wrong_service", "unresponsive"]


@dataclass(frozen=True, slots=True)
class ServerProbe:
    status: ServerStatus
    healthcheck: str
    detail: str


def read_local_http(port: int, path: str, *, timeout_seconds: float) -> tuple[int | None, str]:
    connection = HTTPConnection("127.0.0.1", port, timeout=timeout_seconds)
    try:
        connect_error = connect_local_http(connection)
        if connect_error is not None:
            return None, connect_error
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8")
    except TimeoutError:
        return None, "response_timeout"
    except (HTTPException, OSError, UnicodeDecodeError) as error:
        return None, str(error)
    finally:
        connection.close()


def connect_local_http(connection: HTTPConnection) -> str | None:
    try:
        connection.connect()
    except ConnectionRefusedError:
        return "connection_refused"
    except TimeoutError:
        return "connect_timeout"
    except OSError as error:
        detail = str(error)
        if is_connection_refused_detail(detail):
            return detail
        return "connect_error"
    return None


def probe_from_transport_error(healthcheck: str, detail: str) -> ServerProbe:
    if is_connection_refused_detail(detail):
        return ServerProbe(status="not_running", healthcheck=healthcheck, detail=detail)
    if detail == "connect_timeout":
        return ServerProbe(status="not_running", healthcheck=healthcheck, detail=detail)
    if detail in {"response_timeout", "timeout"}:
        return ServerProbe(status="unresponsive", healthcheck=healthcheck, detail=detail)
    return ServerProbe(status="wrong_service", healthcheck=healthcheck, detail="invalid_response")


def is_connection_refused_detail(detail: str) -> bool:
    return detail in {"connection_refused", str(errno.ECONNREFUSED)} or "10061" in detail


def wait_for_server(
    port: int,
    probe_server: Callable[[int], ServerProbe],
    *,
    wait_seconds: float = SERVER_START_WAIT_SECONDS,
    poll_seconds: float = SERVER_START_POLL_SECONDS,
) -> ServerProbe:
    deadline = time.monotonic() + wait_seconds
    probe = probe_server(port)
    while probe.status != "running" and time.monotonic() < deadline:
        time.sleep(poll_seconds)
        probe = probe_server(port)
    return probe


def start_local_server(
    server_path: str,
    script_dir: os.PathLike[str],
    args: Sequence[str],
) -> int:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, server_path, *args],
        cwd=script_dir,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    return process.pid


def server_probe_json(probe: ServerProbe, *, default_port: int) -> dict[str, JsonValue]:
    return {
        "status": probe.status,
        "healthcheck": probe.healthcheck,
        "detail": probe.detail,
        "port": port_from_healthcheck(probe.healthcheck, default_port=default_port),
    }


def port_from_healthcheck(healthcheck: str, *, default_port: int) -> int:
    prefix = "http://127.0.0.1:"
    if not healthcheck.startswith(prefix):
        return default_port
    raw_port = healthcheck.removeprefix(prefix).split("/", maxsplit=1)[0]
    try:
        return int(raw_port)
    except ValueError:
        return default_port


def next_action_for_probe(
    status: ServerStatus,
    *,
    running: str,
    not_running: str,
    wrong_service: str,
    unresponsive: str,
) -> str:
    match status:
        case "running":
            return running
        case "not_running":
            return not_running
        case "wrong_service":
            return wrong_service
        case "unresponsive":
            return unresponsive
    assert_never(status)


_probe_from_transport_error = probe_from_transport_error
