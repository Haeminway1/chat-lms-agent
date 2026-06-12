from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from chat_lms_agent.side_panel import VIEWS
from chat_lms_agent.side_panel_design_lint import side_panel_design_lint
from chat_lms_agent.side_panel_design_verify_contract import (
    VerifyEvidenceParts,
    VerifyFixtures,
    VerifyMode,
    build_verify_evidence,
    build_verify_fixtures,
    checked_modes_from_artifact,
)
from chat_lms_agent.side_panel_design_verify_server import fixture_server

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError:
    PlaywrightError = RuntimeError
    sync_playwright = None

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Protocol

    from chat_lms_agent.state import JsonValue

    class _BrowserPage(Protocol):
        def set_viewport_size(self, viewport_size: dict[str, int]) -> None: ...

        def goto(self, url: str, *, wait_until: str) -> object: ...

        def evaluate(self, expression: str) -> JsonValue: ...

_RUNTIME_DISABLE_ENV: Final = "CHAT_LMS_AGENT_DESIGN_VERIFY_DISABLE_BROWSER"
_RUNTIME_INSTALL_HINT: Final = (
    "Install Playwright Chromium for local verification: uv run playwright install chromium "
    "or uv run python -m playwright install chromium."
)


@dataclass(frozen=True, slots=True)
class _RuntimeMissing:
    detail: str


type _BrowserResult = list[dict[str, JsonValue]] | _RuntimeMissing


def side_panel_design_verify(
    artifact_path: Path,
    view: str,
    mode: VerifyMode,
) -> tuple[int, dict[str, JsonValue]]:
    if view not in VIEWS:
        return 2, {"status": "ERROR", "error_code": "UNKNOWN_SIDE_PANEL_VIEW", "view": view}
    try:
        artifact_html = artifact_path.read_text(encoding="utf-8-sig")
    except OSError as error:
        return 1, {"status": "ERROR", "error_code": "INVALID_ARTIFACT", "message": str(error)}
    lint_code, lint_payload = side_panel_design_lint(artifact_path, mode)
    checked_modes = checked_modes_from_artifact(artifact_html, mode)
    lint_check = _lint_check(lint_code, lint_payload)
    if lint_code != 0:
        evidence = build_verify_evidence(
            VerifyEvidenceParts(
                artifact_path=artifact_path,
                view=view,
                mode=mode,
                checked_modes=checked_modes,
                lint_payload=lint_payload,
                checks=[lint_check],
            ),
        )
        return 2, evidence
    fixtures = build_verify_fixtures(view)
    browser_result = _browser_checks(artifact_html, fixtures, checked_modes)
    match browser_result:
        case _RuntimeMissing() as missing:
            return 5, _runtime_missing_payload(missing.detail)
        case list() as checks:
            checks_payload: list[JsonValue] = [lint_check, *checks]
            evidence = build_verify_evidence(
                VerifyEvidenceParts(
                    artifact_path=artifact_path,
                    view=view,
                    mode=mode,
                    checked_modes=checked_modes,
                    lint_payload=lint_payload,
                    checks=checks_payload,
                ),
            )
            return (0 if evidence["status"] == "PASS" else 2), evidence


def _browser_checks(
    artifact_html: str,
    fixtures: VerifyFixtures,
    checked_modes: tuple[str, ...],
) -> _BrowserResult:
    if os.environ.get(_RUNTIME_DISABLE_ENV) == "1":
        return _RuntimeMissing("runtime disabled by environment")
    if sync_playwright is None:
        return _RuntimeMissing("playwright package is not importable")
    try:
        with (
            fixture_server(artifact_html, fixtures.fixture_a) as server,
            sync_playwright() as playwright,
        ):
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 372, "height": 760})
                url = server.base_url + "/"
                _ = page.goto(url, wait_until="networkidle")
                text_a = page.inner_text("body")
                server.set_payload(fixtures.fixture_b)
                _ = page.goto(url, wait_until="networkidle")
                text_b = page.inner_text("body")
                checks = [
                    _markers_check("fixture_a_markers", fixtures.markers_a, text_a),
                    _fixture_swap_check(
                        fixtures.markers_a,
                        fixtures.markers_b,
                        text_b,
                    ),
                ]
                if "panel" in checked_modes:
                    checks.append(_scroll_check(page, "panel", 372, 760, url))
                if "fullscreen" in checked_modes:
                    checks.append(_scroll_check(page, "fullscreen", 1440, 900, url))
                return checks
            finally:
                browser.close()
    except PlaywrightError as error:
        return _RuntimeMissing(str(error))


def _lint_check(lint_code: int, lint_payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return {
        "id": "design_lint",
        "status": "PASS" if lint_code == 0 else "FAIL",
        "details": lint_payload,
    }


def _markers_check(check_id: str, markers: tuple[str, ...], text: str) -> dict[str, JsonValue]:
    missing = [marker for marker in markers if marker not in text]
    missing_values: list[JsonValue] = [*missing]
    return {
        "id": check_id,
        "status": "PASS" if not missing else "FAIL",
        "missing_markers": missing_values,
    }


def _fixture_swap_check(
    markers_a: tuple[str, ...],
    markers_b: tuple[str, ...],
    text: str,
) -> dict[str, JsonValue]:
    missing_b = [marker for marker in markers_b if marker not in text]
    remaining_a = [marker for marker in markers_a if marker in text]
    missing_b_values: list[JsonValue] = [*missing_b]
    remaining_a_values: list[JsonValue] = [*remaining_a]
    return {
        "id": "fixture_b_replaces_a",
        "status": "PASS" if not missing_b and not remaining_a else "FAIL",
        "missing_b_markers": missing_b_values,
        "remaining_a_markers": remaining_a_values,
    }


def _scroll_check(
    page: object,
    mode: str,
    width: int,
    height: int,
    url: str,
) -> dict[str, JsonValue]:
    typed_page = cast("_BrowserPage", page)
    typed_page.set_viewport_size({"width": width, "height": height})
    _ = typed_page.goto(url, wait_until="networkidle")
    raw_metrics = typed_page.evaluate(
        """() => {
            const element = document.scrollingElement || document.documentElement;
            return {
                scrollWidth: element.scrollWidth,
                clientWidth: element.clientWidth
            };
        }""",
    )
    metrics = _metrics(raw_metrics)
    scroll_width = metrics.get("scroll_width", 0)
    client_width = metrics.get("client_width", 0)
    return {
        "id": f"{mode}_horizontal_scroll",
        "status": "PASS" if scroll_width <= client_width else "FAIL",
        "viewport": {"width": width, "height": height},
        "scroll_width": scroll_width,
        "client_width": client_width,
    }


def _metrics(raw_metrics: JsonValue) -> dict[str, int]:
    if not isinstance(raw_metrics, dict):
        return {"scroll_width": 0, "client_width": 0}
    scroll_width = raw_metrics.get("scrollWidth")
    client_width = raw_metrics.get("clientWidth")
    return {
        "scroll_width": scroll_width if isinstance(scroll_width, int) else 0,
        "client_width": client_width if isinstance(client_width, int) else 0,
    }


def _runtime_missing_payload(detail: str) -> dict[str, JsonValue]:
    return {
        "status": "BLOCKED",
        "error_code": "DESIGN_VERIFY_RUNTIME_MISSING",
        "message": "Playwright Chromium is required for side-panel design verification",
        "detail": detail,
        "install_hint": _RUNTIME_INSTALL_HINT,
    }
