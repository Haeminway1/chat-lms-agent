from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Final, Literal, override

from chat_lms_agent.side_panel import TOKEN_AXES

if TYPE_CHECKING:
    from pathlib import Path

    from chat_lms_agent.state import JsonValue

LintMode = Literal["panel", "fullscreen", "all"]
_ERROR_CODE: Final = "INVALID_SIDE_PANEL_DESIGN"
_PANEL_MAX_WIDTH: Final = 480
_TOP_LEVEL_SELECTORS: Final = frozenset(
    {"html", "body", "main", "#app", ".shell", ".side-panel-shell", ".panel-shell", ".app-shell"},
)
_HTTP_REFERENCE: Final[re.Pattern[str]] = re.compile(r"https?://", re.IGNORECASE)
_FETCH_TARGET: Final[re.Pattern[str]] = re.compile(
    r"fetch\s*\(\s*(?P<quote>['\"`])(?P<target>[^'\"`]+)",
    re.IGNORECASE,
)
_CSS_RULE: Final[re.Pattern[str]] = re.compile(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}")
_CSS_PROPERTY: Final[re.Pattern[str]] = re.compile(
    r"(?P<name>[A-Za-z-]+)\s*:\s*(?P<value>[^;]+)",
)
_META: Final[re.Pattern[str]] = re.compile(
    r"<meta\b(?P<attrs>[^>]*)>",
    re.IGNORECASE,
)
_ATTR: Final[re.Pattern[str]] = re.compile(
    r"(?P<name>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*(?P<quote>['\"])(?P<value>.*?)(?P=quote)",
)
_FONT_FAMILY: Final[re.Pattern[str]] = re.compile(
    r"font-family\s*:\s*(?P<stack>[^;{}]+)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _HtmlFacts:
    meta: dict[str, str]
    styles: str
    text: str


class _FactParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self._style_chunks: list[str] = []
        self._in_style: bool = False

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "style":
            self._in_style = True
        if tag.lower() != "meta":
            return
        values = {key.lower(): value for key, value in attrs if value is not None}
        name = values.get("name")
        content = values.get("content")
        if name is not None and content is not None:
            self.meta[name.lower()] = content

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style":
            self._in_style = False

    @override
    def handle_data(self, data: str) -> None:
        if self._in_style:
            self._style_chunks.append(data)

    def facts(self, text: str) -> _HtmlFacts:
        return _HtmlFacts(meta=self.meta, styles="\n".join(self._style_chunks), text=text)


def side_panel_design_lint(artifact_path: Path, mode: LintMode) -> tuple[int, dict[str, JsonValue]]:
    try:
        text = artifact_path.read_text(encoding="utf-8-sig")
    except OSError as error:
        return 1, _error_payload("INVALID_ARTIFACT", [str(error)], mode, ())
    parser = _FactParser()
    parser.feed(text)
    facts = _merge_meta(parser.facts(text))
    declared_modes = _declared_modes(facts)
    checked_modes = _checked_modes(mode, declared_modes)
    errors = _base_errors(facts, declared_modes, mode, checked_modes)
    if "panel" in checked_modes:
        errors.extend(_panel_width_errors(facts.styles))
    if errors:
        return 2, _error_payload(_ERROR_CODE, errors, mode, checked_modes)
    return 0, {
        "status": "PASS",
        "mode": mode,
        "checked_modes": [*checked_modes],
        "errors": [],
        "warnings": [],
    }


def _merge_meta(facts: _HtmlFacts) -> _HtmlFacts:
    meta = dict(facts.meta)
    for item in _META.finditer(facts.text):
        attrs = {
            attr.group("name").lower(): attr.group("value")
            for attr in _ATTR.finditer(item.group("attrs"))
        }
        name = attrs.get("name")
        content = attrs.get("content")
        if name is not None and content is not None:
            meta[name.lower()] = content
    return _HtmlFacts(meta=meta, styles=facts.styles, text=facts.text)


def _declared_modes(facts: _HtmlFacts) -> tuple[str, ...]:
    modes = facts.meta.get("side-panel-modes")
    if modes is None:
        return ()
    return tuple(part for part in modes.split() if part)


def _checked_modes(mode: LintMode, declared_modes: tuple[str, ...]) -> tuple[str, ...]:
    match mode:
        case "panel":
            return ("panel",)
        case "fullscreen":
            return ("fullscreen",)
        case "all":
            if "fullscreen" in declared_modes:
                return ("panel", "fullscreen")
            return ("panel",)


def _base_errors(
    facts: _HtmlFacts,
    declared_modes: tuple[str, ...],
    mode: LintMode,
    checked_modes: tuple[str, ...],
) -> list[str]:
    errors: list[str] = []
    if "viewport" not in facts.meta:
        errors.append("missing viewport meta")
    if not declared_modes:
        errors.append("missing side-panel-modes meta")
    elif "panel" not in declared_modes:
        errors.append("side-panel-modes meta must include panel")
    if mode == "fullscreen" and "fullscreen" not in declared_modes:
        errors.append("fullscreen mode requested but not declared")
    errors.extend(_offline_errors(facts.text))
    errors.extend(_overflow_errors(facts.styles))
    errors.extend(_token_errors(facts.styles))
    errors.extend(_font_errors(facts.styles))
    errors.extend(_theme_errors(facts.styles))
    if not _has_relative_api_fetch(facts.text):
        errors.append("missing fetch call targeting a relative /api/ path")
    if "fullscreen" in checked_modes:
        errors.extend(_fullscreen_errors(facts.styles))
    return errors


def _offline_errors(text: str) -> list[str]:
    if _HTTP_REFERENCE.search(text):
        return ["external http(s) reference is forbidden"]
    return []


def _overflow_errors(styles: str) -> list[str]:
    errors: list[str] = []
    for selector, declarations in _css_declarations(styles):
        if not _selector_matches(selector, _TOP_LEVEL_SELECTORS):
            continue
        value = declarations.get("overflow-x")
        if value in {"auto", "scroll"}:
            errors.append(f"overflow-x:{value} is forbidden on {_selector_label(selector)}")
    return errors


def _panel_width_errors(styles: str) -> list[str]:
    errors: list[str] = []
    for selector, declarations in _css_declarations(styles):
        if not _selector_matches(selector, _TOP_LEVEL_SELECTORS):
            continue
        width = _pixel_width(declarations.get("width"))
        if width is not None and width > _PANEL_MAX_WIDTH:
            message = (
                f"fixed width {width}px exceeds panel max width {_PANEL_MAX_WIDTH}px "
                f"on {_selector_label(selector)}"
            )
            errors.append(
                message,
            )
    return errors


def _fullscreen_errors(styles: str) -> list[str]:
    errors: list[str] = []
    for selector, declarations in _css_declarations(styles):
        if _selector_matches(selector, frozenset({"html", "body"})):
            value = declarations.get("overflow-x")
            if value in {"auto", "scroll"}:
                errors.append(f"fullscreen forbids document overflow-x:{value}")
    return errors


def _token_errors(styles: str) -> list[str]:
    lower_styles = styles.lower()
    missing = [
        axis
        for axis in TOKEN_AXES
        if re.search(rf"--[-a-z0-9_]*{re.escape(axis.lower())}\b", lower_styles) is None
    ]
    if missing:
        return ["missing CSS custom property for TOKEN_AXES axis: " + ", ".join(missing)]
    return []


def _font_errors(styles: str) -> list[str]:
    for match in _FONT_FAMILY.finditer(styles):
        stack = match.group("stack").strip()
        first = stack.split(",", maxsplit=1)[0].strip().strip("\"'").lower()
        lower_stack = stack.lower()
        fallbacks = ("-apple-system", "system-ui", "sans-serif")
        has_system = any(fallback in lower_stack for fallback in fallbacks)
        if first in {"pretendard variable", "pretendard"} and has_system:
            return []
    return ["font stack must start with Pretendard and include a system fallback"]


def _theme_errors(styles: str) -> list[str]:
    lower_styles = styles.lower()
    has_light = "--token-theme: light" in lower_styles or '[data-theme="light"]' in lower_styles
    has_dark = (
        "prefers-color-scheme: dark" in lower_styles or '[data-theme="dark"]' in lower_styles
    )
    if not has_light:
        return ["missing light theme block"]
    if not has_dark:
        return ["missing dark theme block"]
    return []


def _has_relative_api_fetch(text: str) -> bool:
    return any(match.group("target").startswith("/api/") for match in _FETCH_TARGET.finditer(text))


def _css_declarations(styles: str) -> list[tuple[str, dict[str, str]]]:
    rules: list[tuple[str, dict[str, str]]] = []
    for match in _CSS_RULE.finditer(styles):
        declarations = {
            item.group("name").lower(): item.group("value").strip().lower()
            for item in _CSS_PROPERTY.finditer(match.group("body"))
        }
        rules.append((match.group("selectors").strip(), declarations))
    return rules


def _selector_matches(selector: str, targets: frozenset[str]) -> bool:
    return any(_selector_label(part) in targets for part in selector.split(","))


def _selector_label(selector: str) -> str:
    tokens = selector.strip().split()
    if not tokens:
        return selector.strip()
    return tokens[-1].strip()


def _pixel_width(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.fullmatch(r"(?P<width>\d+)px", value.strip())
    if match is None:
        return None
    return int(match.group("width"))


def _error_payload(
    error_code: str,
    errors: list[str],
    mode: LintMode,
    checked_modes: tuple[str, ...],
) -> dict[str, JsonValue]:
    return {
        "status": "ERROR",
        "error_code": error_code,
        "mode": mode,
        "checked_modes": [*checked_modes],
        "errors": [*errors],
    }
