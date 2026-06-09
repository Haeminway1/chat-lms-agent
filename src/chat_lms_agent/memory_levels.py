from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


def memory_levels_payload() -> dict[str, JsonValue]:
    levels: list[JsonValue] = [
        {
            "id": "conversation_ref",
            "tencentdb_layer": "L0",
            "hydrated_by_default": False,
            "requires_review": False,
            "purpose": "pointer to raw private source or offload id",
        },
        {
            "id": "atom",
            "tencentdb_layer": "L1",
            "hydrated_by_default": True,
            "requires_review": True,
            "purpose": "small reviewed fact",
        },
        {
            "id": "scenario",
            "tencentdb_layer": "L2",
            "hydrated_by_default": True,
            "requires_review": True,
            "purpose": "recurring workflow or situation",
        },
        {
            "id": "persona_or_policy",
            "tencentdb_layer": "L3",
            "hydrated_by_default": True,
            "requires_review": True,
            "purpose": "stable teacher preference or academy policy",
        },
        {
            "id": "failure_pattern",
            "tencentdb_layer": "L1",
            "hydrated_by_default": True,
            "requires_review": True,
            "purpose": "repeated error and prevention rule",
        },
        {
            "id": "tool_knowledge",
            "tencentdb_layer": "L1",
            "hydrated_by_default": True,
            "requires_review": True,
            "purpose": "reusable command or tool usage rule",
        },
    ]
    return {
        "status": "PASS",
        "schema_version": "memory-levels-v1",
        "source_reference": "TencentDB-Agent-Memory structural mapping",
        "levels": levels,
    }
