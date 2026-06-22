from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chat_lms_agent.state import JsonValue

HOMEWORK_HEADER = "숙제"
MANAGER_LABEL = "담당 관리자"


@dataclass(frozen=True, slots=True)
class HomeworkBlock:
    sheet_class: str
    db_class: str
    footer_row: int
    students: dict[str, int]


def sheet_rows(payload: dict[str, JsonValue]) -> list[list[str]]:
    raw_values = payload.get("values")
    if not isinstance(raw_values, list):
        message = "current values payload needs a values list"
        raise TypeError(message)
    return [
        [clean(value) for value in raw_row] if isinstance(raw_row, list) else []
        for raw_row in raw_values
    ]


def discover_blocks(
    rows: list[list[str]],
    class_alias_map: dict[str, str],
) -> dict[str, HomeworkBlock]:
    headers = [
        (index, cell(rows, index, 4))
        for index in range(1, len(rows) + 1)
        if cell(rows, index, 1).startswith("NO.") and cell(rows, index, 4)
    ]
    blocks: dict[str, HomeworkBlock] = {}
    for pos, (header_row, sheet_class) in enumerate(headers):
        end_row = headers[pos + 1][0] - 1 if pos + 1 < len(headers) else len(rows)
        block = _block_from_rows(rows, header_row, end_row, sheet_class, class_alias_map)
        if block is not None:
            blocks[block.db_class] = block
    return blocks


def range_a1(sheet_name: str, cell_ref: str) -> str:
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'!{cell_ref}"


def date_tab(lesson_date: str) -> str:
    return str(date.fromisoformat(lesson_date).day)


def cell(rows: list[list[str]], row: int, col: int) -> str:
    if row > len(rows):
        return ""
    values = rows[row - 1]
    if col > len(values):
        return ""
    return values[col - 1]


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _block_from_rows(
    rows: list[list[str]],
    header_row: int,
    end_row: int,
    sheet_class: str,
    class_alias_map: dict[str, str],
) -> HomeworkBlock | None:
    footer_row = 0
    students: dict[str, int] = {}
    for row in range(header_row + 1, end_row + 1):
        if cell(rows, row, 1) == MANAGER_LABEL and cell(rows, row, 9) == HOMEWORK_HEADER:
            footer_row = row
            break
        if cell(rows, row, 1).isdigit() and cell(rows, row, 2):
            students[cell(rows, row, 2)] = row
    if not footer_row:
        return None
    db_class = class_alias_map.get(sheet_class, sheet_class)
    return HomeworkBlock(sheet_class, db_class, footer_row, students)
