#!/usr/bin/env python3
"""Bake the audited formula workbook into a values-only viewer-friendly twin."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import formulas
import openpyxl
from formulas.tokens.operand import XlError

SOURCE = Path("output/exports/VN_Index_Quant_Model_Complete_Architecture.xlsx")
DESTINATION = Path("output/exports/VN_Index_Quant_Model_Complete_Architecture_Values.xlsx")


def evaluated_cells(path: Path) -> dict[tuple[str, str], object]:
    solution = formulas.ExcelModel().loads(str(path)).finish().calculate()
    pattern = re.compile(r"\]([^']+)'!([A-Z]+\d+)$")
    values: dict[tuple[str, str], object] = {}
    for key, result in solution.items():
        match = pattern.search(str(key).upper())
        if not match:
            continue
        try:
            values[(match.group(1), match.group(2))] = result.value.ravel()[0]
        except Exception:
            continue
    return values


def main() -> int:
    if not SOURCE.exists():
        print(f"ERROR: source workbook not found: {SOURCE}", file=sys.stderr)
        return 2

    values = evaluated_cells(SOURCE)
    workbook = openpyxl.load_workbook(SOURCE, data_only=False)
    baked = unresolved = 0
    errors: list[str] = []

    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.data_type != "f":
                    continue
                key = (sheet.title.upper(), cell.coordinate.upper())
                if key not in values:
                    unresolved += 1
                    errors.append(f"unresolved formula: {sheet.title}!{cell.coordinate}")
                    continue
                value = values[key]
                if isinstance(value, XlError):
                    errors.append(f"Excel evaluation error {value}: {sheet.title}!{cell.coordinate}")
                    continue
                if hasattr(value, "item"):
                    value = value.item()
                if isinstance(value, float):
                    value = round(value, 10)
                cell.value = value
                baked += 1

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"Formula cells baked: {baked} | unresolved: {unresolved} | errors: {len(errors)}")
        return 1

    workbook["00_Executive_Dashboard"]["A27"] = (
        "VALUES-BAKED VIEWER COPY — convenient for previews/imports that do not recalculate formulas. "
        "The formula-driven Architecture workbook is the official auditable model."
    )
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(DESTINATION)
    print(f"Generated: {DESTINATION}")
    print(f"Formula cells baked: {baked} | unresolved: {unresolved} | errors: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
