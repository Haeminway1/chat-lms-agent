"""One-time Google consent flow on a loopback listener.

Opens the teacher's browser to the consent screen; Google redirects to
``http://127.0.0.1:<port>`` and the embedded handler captures the code,
which is exchanged for the token. Live-only by design — CI never runs
this; tests cover URL construction and the code exchange via injected
transports.
"""

from __future__ import annotations

import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, override

from chat_lms_agent.gws_auth import GwsAuthError, consent_url, exchange_code_for_token

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

_CONSENT_TIMEOUT_SECONDS = 300.0
_DONE_PAGE = (
    "<html><body><h3>chat-lms: Google 연동이 완료되었습니다."
    " 이 창은 닫으셔도 됩니다.</h3></body></html>"
)


class _CodeCatcher(BaseHTTPRequestHandler):
    code: str | None = None

    def do_GET(self) -> None:
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        codes = params.get("code")
        if codes:
            type(self).code = codes[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        _ = self.wfile.write(_DONE_PAGE.encode("utf-8"))

    @override
    def log_message(self, format: str, *args: object) -> None:
        _ = (format, args)


def run_consent_flow(client_id: str, client_secret: str) -> dict[str, JsonValue]:
    """Open the consent screen and exchange the captured code for a token."""
    _CodeCatcher.code = None
    server = HTTPServer(("127.0.0.1", 0), _CodeCatcher)
    port = server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}"
    url = consent_url(client_id, redirect_uri)
    opened = webbrowser.open(url)
    if not opened:
        # Headless shell: the teacher opens the URL manually; the loopback
        # listener still catches the redirect on this machine.
        print(f"브라우저를 열 수 없습니다. 이 주소를 직접 열어주세요:\n{url}")  # noqa: T201
    server.timeout = _CONSENT_TIMEOUT_SECONDS
    server.handle_request()
    server.server_close()
    code = _CodeCatcher.code
    if not code:
        raise _setup_error(
            error_code="GWS_CONSENT_TIMEOUT",
            message="no consent code received; run chat-lms gws setup again",
        )
    return exchange_code_for_token(client_id, client_secret, code, redirect_uri)


def _setup_error(error_code: str, message: str) -> GwsAuthError:
    return GwsAuthError(error_code, message)
