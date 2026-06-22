from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue


def verification_manifest(
    payload: dict[str, JsonValue],
    post_values: dict[str, JsonValue],
    post_safety: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    values = post_values.get("values", [])
    rows = cast("list[JsonValue]", values) if isinstance(values, list) else []
    data = payload.get("data", [])
    updates = cast("list[JsonValue]", data) if isinstance(data, list) else []
    verified: list[JsonValue] = []
    mismatches: list[JsonValue] = []
    for raw in updates:
        if not isinstance(raw, dict):
            continue
        update = cast("dict[str, JsonValue]", raw)
        expected = _first_update_value(update)
        row, col = _parse_range_cell(str(update.get("range", "")))
        actual = _sheet_cell(rows, row, col)
        ok = actual == expected
        verified.append(
            {"range": update.get("range"), "expected": expected, "actual": actual, "ok": ok},
        )
        if not ok:
            mismatches.append(
                {"range": update.get("range"), "expected": expected, "actual": actual},
            )
    bad_rows = _bad_homework_append_rows(post_safety)
    return {
        "status": "PASS" if not mismatches and not bad_rows else "FAIL",
        "verified_count": len(verified),
        "mismatches": mismatches,
        "bad_p_z_rows": bad_rows,
        "verified": verified,
    }


def _first_update_value(raw: dict[str, JsonValue]) -> str:
    values = raw.get("values")
    if not isinstance(values, list) or not values:
        return ""
    first_row = values[0]
    if not isinstance(first_row, list) or not first_row:
        return ""
    return str(first_row[0]).strip()


def _parse_range_cell(range_a1: str) -> tuple[int, int]:
    cell_ref = range_a1.split("!", 1)[-1]
    letters = "".join(char for char in cell_ref if char.isalpha()).upper()
    digits = "".join(char for char in cell_ref if char.isdigit())
    col = 0
    for letter in letters:
        col = (col * 26) + ord(letter) - 64
    return int(digits), col


def _sheet_cell(rows: list[JsonValue], row: int, col: int) -> str:
    if row > len(rows):
        return ""
    raw_row = rows[row - 1]
    if not isinstance(raw_row, list) or col > len(raw_row):
        return ""
    cells = cast("list[JsonValue]", raw_row)
    return str(cells[col - 1]).strip()


def _bad_homework_append_rows(post_safety: dict[str, JsonValue]) -> list[JsonValue]:
    values = post_safety.get("values", [])
    rows = cast("list[JsonValue]", values) if isinstance(values, list) else []
    result: list[JsonValue] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, list):
            continue
        cells = cast("list[JsonValue]", row)
        joined = "\t".join(str(value) for value in cells)
        if "숙제" in joined and "이행률" in joined:
            result.append({"row": index, "values": cells})
    return result
