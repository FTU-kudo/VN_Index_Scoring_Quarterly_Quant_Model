import openpyxl
import json
import numpy as np

wb = openpyxl.load_workbook("output/exports/VN_Index_Quant_Model_Complete_Architecture.xlsx", data_only=False)

print("=== SHEET VERIFICATION ===")
total_formulas = 0
for name in wb.sheetnames:
    ws = wb[name]
    formulas_in_sheet = 0
    for row in ws.iter_rows(values_only=False):
        for cell in row:
            if cell.value and str(cell.value).startswith("="):
                formulas_in_sheet += 1
                total_formulas += 1
    print(f"Sheet '{name}': {formulas_in_sheet} dynamic Excel formulas")

print(f"\nTOTAL DYNAMIC FORMULAS IN WORKBOOK: {total_formulas}")

# Verify exact values against score_*.json
with open("data/scores/vnindex_quarterly_close.json") as f:
    price_cache = json.load(f)

print("\n=== EXPANDING CALIBRATION RECONCILIATION ===")
# Let's inspect formulas in 05_Composite_Calibration
ws_cal = wb["05_Composite_Calibration"]
print("Sample cell formulas:")
for r in [5, 6, 10, 28]:
    q_cell = ws_cal.cell(row=r, column=1).value
    raw_cell = ws_cal.cell(row=r, column=4).value
    cal_cell = ws_cal.cell(row=r, column=10).value
    alloc_cell = ws_cal.cell(row=r, column=12).value
    print(f"Row {r} -> Q: {q_cell} | Raw: {raw_cell} | Cal: {cal_cell} | Alloc: {alloc_cell}")

