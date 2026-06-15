from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


OFFICIAL_NAME: str = "보조 패널(side panel)"
DESIGN_REFERENCE: str = "user-provided-html-prototype"

VIEWS: tuple[str, ...] = (
    "class_overview",
    "learner_detail",
    "attendance_summary",
    "session_record",
    "homework_status",
)

SECTION_TYPES: tuple[str, ...] = (
    "summary",
    "metric_grid",
    "entity_list",
    "timeline",
    "task_list",
    "action_group",
)

BLOCK_CATALOG: tuple[str, ...] = (
    "SidePanelShell",
    "PanelChrome",
    "PanelHeader",
    "WarningBanner",
    "SummaryBlock",
    "MetricGrid",
    "EntityList",
    "Timeline",
    "TaskList",
    "ActionGroup",
    "SourceCommandsFooter",
    "ViewTabs",
    "ThemeTokens",
    "TweaksPanel",
)


class ViewDraft(TypedDict):
    recommended_variant: str
    required_sections: list[str]


VIEW_DRAFTS: dict[str, ViewDraft] = {
    "class_overview": {
        "recommended_variant": "b",
        "required_sections": ["summary", "metric_grid", "task_list", "action_group"],
    },
    "learner_detail": {
        "recommended_variant": "a",
        "required_sections": ["summary", "timeline", "task_list", "action_group"],
    },
    "attendance_summary": {
        "recommended_variant": "b",
        "required_sections": ["summary", "metric_grid", "entity_list", "action_group"],
    },
    "session_record": {
        "recommended_variant": "c",
        "required_sections": ["summary", "timeline", "action_group"],
    },
    "homework_status": {
        "recommended_variant": "a",
        "required_sections": ["summary", "entity_list", "task_list", "action_group"],
    },
}


def _json_strings(values: tuple[str, ...] | list[str]) -> list[JsonValue]:
    return [*values]


TOKEN_AXES: dict[str, JsonValue] = {
    "accent": {"type": "hex_color", "default": "#3182F6"},
    "fontSize": {"type": "integer", "min": 13, "max": 18},
    "density": {"type": "enum", "allowed": _json_strings(("compact", "comfy", "roomy"))},
    "round": {"type": "enum", "allowed": _json_strings(("sharp", "soft", "round"))},
    "theme": {"type": "enum", "allowed": _json_strings(("light", "dark", "system"))},
}


def side_panel_contract_shape() -> dict[str, JsonValue]:
    wordbook_route: dict[str, JsonValue] = {
        "triggers": _json_strings(
            (
                "단어 html 패널",
                "단어 HTML 패널",
                "수업 단어장",
                "단어 현황",
                "단어 보고",
                "단어 조회",
                "단어 리스트",
                "모르는 단어",
            ),
        ),
        "first_command": (
            "side-panel wordbook open-plan --student <name> "
            "--profile-root <root> --json"
        ),
        "ensure_command": (
            "side-panel wordbook ensure-server --profile-root <root> --json"
        ),
        "browser_action": "open browser_url with Browser plugin",
        "file_search_policy": "do_not_rg_before_cli_route",
        "wrong_server_policy": "report port conflict before opening",
    }
    traits: dict[str, JsonValue] = {
        "required": _json_strings(("header_metadata", "warning_first", "summary_first")),
        "recommended": _json_strings(("A/B/C", "light_dark_themes", "source_command_footer")),
        "optional": _json_strings(("privacy_mark", "status_indicator")),
        "out_of_scope": _json_strings(("agent-owned_html", "agent-owned_css")),
    }
    return {
        "official_name": OFFICIAL_NAME,
        "views": _json_strings(VIEWS),
        "section_types": _json_strings(SECTION_TYPES),
        "design_reference": DESIGN_REFERENCE,
        "user_owned_html_css": True,
        "token_axes": TOKEN_AXES,
        "traits": traits,
        "runtime_routes": {"lesson_wordbook": wordbook_route},
    }


def side_panel_spec_json() -> dict[str, JsonValue]:
    payload = side_panel_contract_shape()
    payload["status"] = "PASS"
    return payload


def side_panel_blocks_json() -> dict[str, JsonValue]:
    return {"status": "PASS", "blocks": _json_strings(BLOCK_CATALOG)}


def side_panel_view_draft(view: str) -> dict[str, JsonValue]:
    config = VIEW_DRAFTS.get(view)
    if config is None:
        return {
            "status": "PROPOSAL_REQUIRED",
            "view": view,
            "proposal": (
                "Create a design reference entry, proposal note, and memory/decision "
                "record before introducing a new view."
            ),
            "memory_obligation": f"SIDE_PANEL_MEMORY_REQUIRED:side_panel:view:{view}",
        }
    return {
        "status": "PASS",
        "view": view,
        "recommended_variant": config["recommended_variant"],
        "required_sections": _json_strings(config["required_sections"]),
        "memory_obligation": f"SIDE_PANEL_MEMORY_REQUIRED:side_panel:view:{view}",
    }
