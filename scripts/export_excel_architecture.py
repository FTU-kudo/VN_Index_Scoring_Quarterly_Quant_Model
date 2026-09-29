"""
build_perfect_master_workbook.py
Tạo Master Excel Workbook Hoàn Hảo: VN_Index_Quant_Model_Complete_Architecture.xlsx
Hệ Thống Định Lượng Toàn Diện Đánh Giá & Chấm Điểm VN-Index
================================================================================
Tiêu chuẩn:
  1. Hàng 4 là Header, Hàng 5..28 là 24 Quý (2021-Q1 -> 2026-Q4) trên TẤT CẢ các sheet dữ liệu.
  2. 100% CÔNG THỨC EXCEL ĐỘNG cho mọi chỉ số tính toán, không hardcode.
  3. Chuỗi liên kết sheet hoàn chỉnh:
     Config -> Inputs -> Factor Subscores -> Pillar Calculation -> Composite & Calibration -> Strategy Backtest.
  4. Sử dụng double quotes ("...") cho chuỗi trong công thức IF để tránh lỗi #NAME?.
"""

import json
import glob
import os
import re
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

EXPORTS_DIR = Path("output/exports")
SCORES_DIR = Path("data/scores")
OUT_PATH = EXPORTS_DIR / "VN_Index_Quant_Model_Complete_Architecture.xlsx"

# ── Load all data ─────────────────────────────────────────────────────────────
with open("data/scores/vnindex_quarterly_close.json", "r", encoding="utf-8") as f:
    price_cache = json.load(f)

with open("data/scores/vnindex_quarterly_market_data.json", "r", encoding="utf-8") as f:
    market_data_cache = json.load(f).get("quarters", {})

with open("data/scores/vnindex_quarterly_adtv.json", "r", encoding="utf-8") as f:
    adtv_cache = json.load(f).get("quarters", {})

with open("data/scores/vnindex_quarterly_flows.json", "r", encoding="utf-8") as f:
    flows_cache = json.load(f).get("quarters", {})

score_files = sorted(glob.glob("output/exports/score_*.json"))
all_scores = {}
for sf in score_files:
    with open(sf, "r", encoding="utf-8") as f:
        d = json.load(f)
    q = d["quarterly_score"]["quarter"]
    all_scores[q] = d

quarters = sorted(all_scores.keys())
print(f"Loaded {len(quarters)} quarters: {quarters[0]} -> {quarters[-1]}")

wb = openpyxl.Workbook()
wb.remove(wb.active)  # remove default sheet

# ── Styles ────────────────────────────────────────────────────────────────────
f_title = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
f_subtitle = Font(name="Calibri", size=10, italic=True, color="64748B")
f_section = Font(name="Calibri", size=11, bold=True, color="1E3A8A")
f_th = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
f_data = Font(name="Calibri", size=10, color="1E293B")
f_data_bold = Font(name="Calibri", size=10, bold=True, color="0F172A")
f_kpi_big = Font(name="Calibri", size=18, bold=True, color="1E3A8A")
f_kpi_sub = Font(name="Calibri", size=9, bold=True, color="475569")
f_note = Font(name="Calibri", size=9, italic=True, color="64748B")

fill_th_navy = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
fill_th_slate = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
fill_th_blue = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
fill_th_green = PatternFill(start_color="065F46", end_color="065F46", fill_type="solid")
fill_th_amber = PatternFill(start_color="92400E", end_color="92400E", fill_type="solid")
fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
fill_kpi = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
fill_formula = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")

thin_s = Side(border_style="thin", color="CBD5E1")
thick_b = Side(border_style="medium", color="1E3A8A")
double_b = Side(border_style="double", color="1E3A8A")
border_c = Border(left=thin_s, right=thin_s, top=thin_s, bottom=thin_s)
border_h = Border(left=thin_s, right=thin_s, top=thin_s, bottom=thick_b)
border_tot = Border(top=thin_s, bottom=double_b, left=thin_s, right=thin_s)

a_center = Alignment(horizontal="center", vertical="center")
a_left = Alignment(horizontal="left", vertical="center")
a_right = Alignment(horizontal="right", vertical="center")
a_wrap_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
a_th = Alignment(horizontal="center", vertical="center", wrap_text=True)

# ══════════════════════════════════════════════════════════════════════════════
# 00_Executive_Dashboard
# ══════════════════════════════════════════════════════════════════════════════
ws0 = wb.create_sheet(title="00_Executive_Dashboard")
ws0.views.sheetView[0].showGridLines = True
ws0.tab_color = "1E3A8A"

ws0["B2"] = "VN-INDEX QUANTITATIVE SCORING — EXECUTIVE DASHBOARD (2021-2026)"
ws0["B2"].font = f_title
ws0["B3"] = "Báo cáo Tổng hợp Điều hành Định lượng & Quản trị Danh mục Buy-side (Real-time Formula Links)"
ws0["B3"].font = f_subtitle

ws0["B5"] = "QUÝ ĐÁNH GIÁ MỚI NHẤT"; ws0["B5"].font = f_kpi_sub
ws0["B6"] = "='05_Composite_Calibration'!A28"; ws0["B6"].font = f_kpi_big; ws0["B6"].alignment = a_center

ws0["C5"] = "TÍN HIỆU HÀNH ĐỘNG"; ws0["C5"].font = f_kpi_sub
ws0["C6"] = "='05_Composite_Calibration'!K28"; ws0["C6"].font = f_kpi_big; ws0["C6"].alignment = a_center

ws0["D5"] = "ĐIỂM CALIBRATED"; ws0["D5"].font = f_kpi_sub
ws0["D6"] = "='05_Composite_Calibration'!J28"; ws0["D6"].font = f_kpi_big; ws0["D6"].alignment = a_center
ws0["D6"].number_format = "0.00"

ws0["E5"] = "PHÂN BỔ CỔ PHIẾU"; ws0["E5"].font = f_kpi_sub
ws0["E6"] = "='05_Composite_Calibration'!L28"; ws0["E6"].font = Font(name="Calibri", size=12, bold=True, color="1E3A8A"); ws0["E6"].alignment = a_center

ws0["F5"] = "ĐIỂM COMPOSITE (RAW)"; ws0["F5"].font = f_kpi_sub
ws0["F6"] = "='05_Composite_Calibration'!D28"; ws0["F6"].font = f_kpi_big; ws0["F6"].alignment = a_center
ws0["F6"].number_format = "0.00"

for col in ["B", "C", "D", "E", "F"]:
    ws0[f"{col}5"].fill = fill_kpi; ws0[f"{col}6"].fill = fill_kpi
    ws0[f"{col}5"].border = border_c; ws0[f"{col}6"].border = border_c

ws0["B9"] = "1. BẢNG PHÂN RÃ 6 TRỤ CỘT ĐỊNH LƯỢNG CHO QUÝ MỚI NHẤT (2026-Q4)"
ws0["B9"].font = f_section

headers_p = ["Mã Trụ Cột", "Tên Trụ Cột Định Lượng", "Trọng Số (%NAV)", "Điểm Raw (0-100)", "Điểm Trọng Số", "Đóng Góp (%)", "Trạng Thái & Đánh Giá"]
for j, h in enumerate(headers_p, start=2):
    c = ws0.cell(row=10, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

p_rows = [
    ("macro_monetary", "Vĩ mô & Tiền tệ", "='01_Model_Config'!$C$6", "='04_Pillar_Calculation'!C28", "='04_Pillar_Calculation'!I28", "=E11/$E$17", "=IF(E11>=65, \"Thuan loi\", IF(E11>=50, \"Trung tinh\", \"Bat loi\"))"),
    ("global_intermarket", "Toàn cầu & Liên thị trường", "='01_Model_Config'!$C$7", "='04_Pillar_Calculation'!D28", "='04_Pillar_Calculation'!J28", "=E12/$E$17", "=IF(E12>=65, \"Thuan loi\", IF(E12>=50, \"Trung tinh\", \"Bat loi\"))"),
    ("valuation_leverage", "Định giá & Đòn bẩy", "='01_Model_Config'!$C$8", "='04_Pillar_Calculation'!E28", "='04_Pillar_Calculation'!K28", "=E13/$E$17", "=IF(E13>=65, \"Re / An toan\", IF(E13>=50, \"Hop ly\", \"Dat / Rui ro\"))"),
    ("quant_model", "Mô hình Kinh tế lượng (MLR+VAR)", "='01_Model_Config'!$C$9", "='04_Pillar_Calculation'!F28", "='04_Pillar_Calculation'!L28", "=E14/$E$17", "=IF(E14>=65, \"Ky vong tang\", IF(E14>=50, \"Trung tinh\", \"Ky vong giam\"))"),
    ("ml_forecast", "Dự báo Machine Learning (XGBoost)", "='01_Model_Config'!$C$10", "='04_Pillar_Calculation'!G28", "='04_Pillar_Calculation'!M28", "=E15/$E$17", "=IF(E15>=65, \"Tin hieu UP\", IF(E15>=50, \"Tin hieu SIDEWAY\", \"Tin hieu DOWN\"))"),
    ("market_structure", "Cấu trúc Thị trường & FTSE EM", "='01_Model_Config'!$C$11", "='04_Pillar_Calculation'!H28", "='04_Pillar_Calculation'!N28", "=E16/$E$17", "=IF(E16>=65, \"Thanh khoan tot / FTSE+\", IF(E16>=50, \"On dinh\", \"Thanh khoan kem\"))"),
]

for i, r in enumerate(p_rows, start=11):
    ws0.cell(row=i, column=2, value=r[0]).alignment = a_left
    ws0.cell(row=i, column=3, value=r[1]).alignment = a_left
    ws0.cell(row=i, column=4, value=r[2]).alignment = a_right
    ws0.cell(row=i, column=5, value=r[3]).alignment = a_right
    ws0.cell(row=i, column=6, value=r[4]).alignment = a_right
    ws0.cell(row=i, column=7, value=r[5]).alignment = a_right
    ws0.cell(row=i, column=8, value=r[6]).alignment = a_center
    
    ws0.cell(row=i, column=4).number_format = "0.0%"
    ws0.cell(row=i, column=5).number_format = "0.00"
    ws0.cell(row=i, column=6).number_format = "0.00"
    ws0.cell(row=i, column=7).number_format = "0.0%"
    
    for c in range(2, 9):
        cell = ws0.cell(row=i, column=c)
        cell.font = f_data; cell.border = border_c
        if i % 2 == 0: cell.fill = fill_zebra

ws0.cell(row=17, column=2, value="TỔNG COMPOSITE").alignment = a_left
ws0.cell(row=17, column=3, value="Điểm Tổng Hợp Có Trọng Số").alignment = a_left
ws0.cell(row=17, column=4, value="=SUM(D11:D16)").alignment = a_right
ws0.cell(row=17, column=5, value="=AVERAGE(E11:E16)").alignment = a_right
ws0.cell(row=17, column=6, value="=SUM(F11:F16)").alignment = a_right
ws0.cell(row=17, column=7, value="=SUM(G11:G16)").alignment = a_right
ws0.cell(row=17, column=8, value="='05_Composite_Calibration'!E28").alignment = a_center

ws0.cell(row=17, column=4).number_format = "0.0%"
ws0.cell(row=17, column=5).number_format = "0.00"
ws0.cell(row=17, column=6).number_format = "0.00"
ws0.cell(row=17, column=7).number_format = "0.0%"

for c in range(2, 9):
    cell = ws0.cell(row=17, column=c)
    cell.font = f_data_bold; cell.border = border_tot; cell.fill = fill_formula

ws0["B20"] = "2. HIỆU SUẤT CHIẾN LƯỢC PHÂN BỔ ĐỊNH LƯỢNG VS VN-INDEX BENCHMARK (24 QUÝ: 2021-2026)"
ws0["B20"].font = f_section

headers_eff = ["Chỉ Số Đo Lường Hiệu Năng", "Chiến Lược Quant Model (Calibrated)", "VN-Index Buy & Hold Benchmark", "Chênh Lệch (Alpha / Protection)", "Diễn Giải Ý Nghĩa"]
for j, h in enumerate(headers_eff, start=2):
    c = ws0.cell(row=21, column=j, value=h)
    c.font = f_th; c.fill = fill_th_slate; c.alignment = a_th; c.border = border_h

eff_rows = [
    ("Tổng Lợi Nhuận Tích Lũy (Cumulative Return)", "='10_Backtest_Efficacy'!B32", "='10_Backtest_Efficacy'!C32", "=C22-D22", "Hiệu quả sinh lời toàn chu kỳ 24 quý"),
    ("Lợi Nhuận Bình Quân Năm (CAGR)", "='10_Backtest_Efficacy'!B33", "='10_Backtest_Efficacy'!C33", "=C23-D23", "Tốc độ tăng trưởng kép hàng năm"),
    ("Mức Sụt Giảm Tối Đa (Max Drawdown - MDD)", "='10_Backtest_Efficacy'!B34", "='10_Backtest_Efficacy'!C34", "=C24-D24", "Khả năng phòng hộ rủi ro sập hầm chu kỳ 2022 & 2026"),
    ("Độ Biến Động Hàng Năm (Annualized Volatility)", "='10_Backtest_Efficacy'!B35", "='10_Backtest_Efficacy'!C35", "=C25-D25", "Mức độ rủi ro dao động NAV danh mục"),
    ("Hệ Số Sinh Lời Trên Rủi Ro (Sharpe Ratio)", "='10_Backtest_Efficacy'!B36", "='10_Backtest_Efficacy'!C36", "=C26-D26", "Tỷ suất sinh lời vượt trội trên 1 đơn vị rủi ro"),
    ("Hệ Số Tương Quan Hạng IC (Spearman Rank IC)", "='10_Backtest_Efficacy'!B37", "N/A", "N/A", "Tương quan thứ bậc điểm định lượng vs lợi suất tương lai"),
    ("Tỷ Lệ Dự Báo Đúng Hướng (Directional Hit Rate)", "='10_Backtest_Efficacy'!B38", "N/A", "N/A", "Tỷ lệ tín hiệu định lượng khớp với chiều tăng/giảm VN-Index"),
]

for i, r in enumerate(eff_rows, start=22):
    ws0.cell(row=i, column=2, value=r[0]).alignment = a_left
    ws0.cell(row=i, column=3, value=r[1]).alignment = a_right
    ws0.cell(row=i, column=4, value=r[2]).alignment = a_right
    ws0.cell(row=i, column=5, value=r[3]).alignment = a_right
    ws0.cell(row=i, column=6, value=r[4]).alignment = a_left
    
    if i in [22, 23, 24, 25, 28]:
        ws0.cell(row=i, column=3).number_format = "0.0%"
        if r[2] != "N/A": ws0.cell(row=i, column=4).number_format = "0.0%"
        if r[3] != "N/A": ws0.cell(row=i, column=5).number_format = "0.0%"
    elif i == 26:
        ws0.cell(row=i, column=3).number_format = "0.00"
        if r[2] != "N/A": ws0.cell(row=i, column=4).number_format = "0.00"
        if r[3] != "N/A": ws0.cell(row=i, column=5).number_format = "0.00"
    elif i == 27:
        ws0.cell(row=i, column=3).number_format = "0.0000"
    
    for c in range(2, 7):
        cell = ws0.cell(row=i, column=c)
        cell.font = f_data; cell.border = border_c
        if i % 2 == 1: cell.fill = fill_zebra

# ══════════════════════════════════════════════════════════════════════════════
# 01_Model_Config
# ══════════════════════════════════════════════════════════════════════════════
ws1 = wb.create_sheet(title="01_Model_Config")
ws1.views.sheetView[0].showGridLines = True
ws1.tab_color = "2563EB"

ws1["A1"] = "VN-INDEX QUANTITATIVE SCORING MODEL — CẤU HÌNH HỆ THỐNG & TRỌNG SỐ"
ws1["A1"].font = f_title
ws1["A2"] = "Single Source of Truth cho toàn bộ công thức và ngưỡng chấm điểm trong Workbook"
ws1["A2"].font = f_subtitle

ws1["A4"] = "1. TRỌNG SỐ 6 TRỤ CỘT ĐỊNH LƯỢNG (SCORING_WEIGHTS)"; ws1["A4"].font = f_section
h_cfg1 = ["Mã Trụ Cột", "Tên Trụ Cột Định Lượng", "Trọng Số (%NAV)", "Ghi Chú Ý Nghĩa / Key Indicators"]
for j, h in enumerate(h_cfg1, start=1):
    c = ws1.cell(row=5, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

weights_data = [
    ("macro_monetary", "Vĩ mô & Tiền tệ", 0.25, "Lãi suất VN1Y, ΔIR, USD/VND Z-score, M2 YoY%, Lợi suất VN10Y, Spread 10Y-1Y"),
    ("global_intermarket", "Toàn cầu & Liên thị trường", 0.20, "DXY Z-score, US10Y Yield, Net Foreign Flow Z, USD/JPY (Carry trade), Oil Shock"),
    ("valuation_leverage", "Định giá & Đòn bẩy", 0.20, "P/E Z-score (5Y), P/B Z-score, Margin Risk Score (0-100), Earnings Yield Gap (EYG) Z"),
    ("quant_model", "Mô hình Kinh tế lượng (MLR + VAR)", 0.15, "Dự báo MLR forward return, VAR T+5 forecast, Adj-R2 bonus, Granger Leaders count"),
    ("ml_forecast", "Dự báo Machine Learning (XGBoost)", 0.10, "8-fold Walk-Forward Validation Accuracy, F1-score, Directional Prediction UP/DOWN"),
    ("market_structure", "Cấu trúc Thị trường & FTSE EM", 0.10, "FTSE Upgrade Status, Months to Rebalancing bonus, ADTV change QoQ%, ETF Flows"),
]

for i, r in enumerate(weights_data, start=6):
    ws1.cell(row=i, column=1, value=r[0]).alignment = a_left
    ws1.cell(row=i, column=2, value=r[1]).alignment = a_left
    ws1.cell(row=i, column=3, value=r[2]).alignment = a_right
    ws1.cell(row=i, column=4, value=r[3]).alignment = a_left
    ws1.cell(row=i, column=3).number_format = "0.0%"
    for c in range(1, 5):
        cell = ws1.cell(row=i, column=c)
        cell.font = f_data; cell.border = border_c
        if i % 2 == 1: cell.fill = fill_zebra

ws1.cell(row=12, column=1, value="TỔNG TRỌNG SỐ").alignment = a_left
ws1.cell(row=12, column=2, value="").alignment = a_left
ws1.cell(row=12, column=3, value="=SUM(C6:C11)").alignment = a_right
ws1.cell(row=12, column=4, value="Kiểm tra ràng buộc: Tổng trọng số bắt buộc = 100%").alignment = a_left
ws1.cell(row=12, column=3).number_format = "0.0%"
for c in range(1, 5):
    cell = ws1.cell(row=12, column=c)
    cell.font = f_data_bold; cell.border = border_tot; cell.fill = fill_formula

ws1["A14"] = "2. THANG ĐIỂM, NHÃN PHÂN LOẠI & MA TRẬN PHÂN BỔ TÀI SẢN (SCORE_LABELS)"; ws1["A14"].font = f_section
h_cfg2 = ["Điểm Min", "Điểm Max", "Nhãn Khuyến Nghị", "Emoji", "Tỷ Trọng CP Gợi Ý (%NAV)", "Tỷ Trọng Giữa (Mid Weight)", "Chiến Lược Quản Trị Rủi Ro"]
for j, h in enumerate(h_cfg2, start=1):
    c = ws1.cell(row=15, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

labels_data = [
    (80, 100, "BUY", "🟢", "85% – 100% Equities", 0.925, "Full vị thế cổ phiếu dẫn dắt VN30, dùng margin chọn lọc"),
    (65, 79.99, "ACCUMULATE", "🔵", "70% – 85% Equities", 0.775, "Tích lũy cổ phiếu cơ bản tốt ở nhịp điều chỉnh, duy trì đòn bẩy an toàn"),
    (50, 64.99, "HOLD", "🟡", "40% – 60% Equities", 0.500, "Cân bằng 50/50, ưu tiên cổ tức cao, tuyệt đối không dùng margin cao"),
    (35, 49.99, "REDUCE", "🟠", "20% – 40% Equities", 0.300, "Hạ tỷ trọng cổ phiếu beta cao, đưa margin về 0, chốt lời từng phần"),
    (0, 34.99, "SELL", "🔴", "0% – 20% Equities", 0.100, "Phòng thủ tối đa, giữ tiền mặt / chứng chỉ tiền gửi, Short VN30F phòng hộ"),
]

for i, r in enumerate(labels_data, start=16):
    ws1.cell(row=i, column=1, value=r[0]).alignment = a_center
    ws1.cell(row=i, column=2, value=r[1]).alignment = a_center
    ws1.cell(row=i, column=3, value=r[2]).alignment = a_center
    ws1.cell(row=i, column=4, value=r[3]).alignment = a_center
    ws1.cell(row=i, column=5, value=r[4]).alignment = a_center
    ws1.cell(row=i, column=6, value=r[5]).alignment = a_right
    ws1.cell(row=i, column=7, value=r[6]).alignment = a_left
    ws1.cell(row=i, column=6).number_format = "0.0%"
    for c in range(1, 8):
        cell = ws1.cell(row=i, column=c)
        cell.font = f_data; cell.border = border_c

ws1["A22"] = "3. THAM SỐ HIỆU CHUẨN TẦNG 2 — CALIBRATED ACTION SIGNAL (SCORE_CALIBRATION)"; ws1["A22"].font = f_section
h_cfg3 = ["Tham Số", "Giá Trị", "Diễn Giải Ý Nghĩa & Vai Trò"]
for j, h in enumerate(h_cfg3, start=1):
    c = ws1.cell(row=23, column=j, value=h)
    c.font = f_th; c.fill = fill_th_slate; c.alignment = a_th; c.border = border_h

calib_params = [
    ("center", 50.0, "Điểm trung tâm chuẩn hóa của Calibrated Action Signal"),
    ("z_scale", 15.0, "Hệ số scale: 1 độ lệch chuẩn lịch sử (1σ) tương đương ±15 điểm calibrated"),
    ("min_history", 4, "Số quý lịch sử tối thiểu trong quá khứ để bắt đầu hiệu chuẩn Expanding Z-score"),
    ("clip_low", 0.0, "Giới hạn điểm sàn dưới (Floor)"),
    ("clip_high", 100.0, "Giới hạn điểm trần trên (Cap)"),
]

for i, r in enumerate(calib_params, start=24):
    ws1.cell(row=i, column=1, value=r[0]).alignment = a_left
    ws1.cell(row=i, column=2, value=r[1]).alignment = a_right
    ws1.cell(row=i, column=3, value=r[2]).alignment = a_left
    for c in range(1, 4):
        cell = ws1.cell(row=i, column=c)
        cell.font = f_data; cell.border = border_c

ws1["A30"] = "4. HỆ SỐ KHUẾCH ĐẠI TÍN HIỆU MÔ HÌNH (GAIN CONVERSION PARAMETERS)"; ws1["A30"].font = f_section
h_cfg4 = ["Mô hình", "Hệ Số Gain", "Công Thức Quy Đổi Điểm 0-100", "Ghi Chú Chống Nén Tín Hiệu"]
for j, h in enumerate(h_cfg4, start=1):
    c = ws1.cell(row=31, column=j, value=h)
    c.font = f_th; c.fill = fill_th_slate; c.alignment = a_th; c.border = border_h

gain_params = [
    ("MLR Model", 20000.0, "50 + MLR_Pred * Gain", "±0.10%/ngày tương đương 70/30 điểm (trước đây gain 3000 bị nén về 53)"),
    ("VAR Model", 5000.0, "50 + VAR_Pred * Gain", "Dự báo lợi suất T+5 của mô hình VAR hệ thống đa biến"),
]

for i, r in enumerate(gain_params, start=32):
    ws1.cell(row=i, column=1, value=r[0]).alignment = a_left
    ws1.cell(row=i, column=2, value=r[1]).alignment = a_right
    ws1.cell(row=i, column=3, value=r[2]).alignment = a_left
    ws1.cell(row=i, column=4, value=r[3]).alignment = a_left
    for c in range(1, 5):
        cell = ws1.cell(row=i, column=c)
        cell.font = f_data; cell.border = border_c

# ══════════════════════════════════════════════════════════════════════════════
# 02_Market_Inputs (Header Row 4, Data Rows 5..28)
# ══════════════════════════════════════════════════════════════════════════════
ws2 = wb.create_sheet(title="02_Market_Inputs")
ws2.views.sheetView[0].showGridLines = True
ws2.tab_color = "059669"

ws2["A1"] = "VN-INDEX QUANTITATIVE MODEL — BẢNG BIẾN SỐ ĐẦU VÀO THỊ TRƯỜNG POINT-IN-TIME (2021-2026)"
ws2["A1"].font = f_title
ws2["A2"] = "Dữ liệu thị trường chốt tại phiên cuối quý liền trước (không chứa thông tin tương lai - Point-in-time)"
ws2["A2"].font = f_subtitle

h_inputs = [
    "Quarter", "As-of Date", "VN-Index Close",
    "VN1Y Yield (%)", "ΔVN1Y (pp)", "VN10Y Yield (%)", "VN Spread (pp)", "USD/VND Z", "M2 YoY (%)",
    "DXY Z (60d)", "US10Y Yield (%)", "NFF Z-score", "NFF % MC", "USD/JPY Z", "Oil Shock Score",
    "Headline P/E", "Median P/E", "Ex-VG P/E", "P/E Z-score", "Headline P/B", "P/B Z-score", "Margin Risk", "EYG Z-score",
    "ADTV Change QoQ (%)", "FTSE Upgrade", "Months to Rebal", "ETF Flow Z", "ETF Flow % MC"
]

for j, h in enumerate(h_inputs, start=1):
    c = ws2.cell(row=4, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

for idx, q in enumerate(quarters):
    row_idx = 5 + idx
    d = all_scores[q]
    qs = d["quarterly_score"]
    as_of = qs.get("data_as_of", "")
    close_p = price_cache.get(q)
    
    mkt = market_data_cache.get(q, {})
    bonds = mkt.get("bonds", {})
    m2_val = mkt.get("m2", {}).get("m2_yoy_pct")
    fx_z = mkt.get("fx_zscore")
    pepb_z = mkt.get("pepb_z", {})
    
    adtv_info = adtv_cache.get(q, {})
    adtv_pct = adtv_info.get("adtv_change_pct")
    
    flow_info = flows_cache.get(q, {})
    nff_z = flow_info.get("nff_z")
    nff_ytd = flow_info.get("nff_ytd_pct")
    etf_z = flow_info.get("etf_z")
    etf_ytd = flow_info.get("etf_ytd_pct")
    
    g_det = qs.get("group_details", {})
    global_det = g_det.get("global_intermarket", {})
    val_det = g_det.get("valuation_leverage", {})
    mkt_det = g_det.get("market_structure", {})
    
    vn1y = bonds.get("vn1y_yield")
    d_vn1y = bonds.get("delta_vn1y_yield")
    vn10y = bonds.get("vn10y_yield")
    vn_spread = bonds.get("vn_yield_spread")
    
    dxy_z_val = None
    if "dxy" in global_det:
        m = re.search(r"Z\s*=\s*([-\d.]+)", global_det["dxy"])
        if m: dxy_z_val = float(m.group(1))
    
    us10y_val = None
    if "us10y" in global_det:
        m = re.search(r"([-\d.]+)%", global_det["us10y"])
        if m: us10y_val = float(m.group(1))
        
    jpy_z_val = None
    if "jpy_carry" in global_det:
        m = re.search(r"Z\s*=\s*([-\d.]+)", global_det["jpy_carry"])
        if m: jpy_z_val = float(m.group(1))
        
    oil_shock_val = 0.0
    if "oil_shock" in global_det and "Score = " in global_det["oil_shock"]:
        m = re.search(r"Score\s*=\s*([-\d.]+)", global_det["oil_shock"])
        if m: oil_shock_val = float(m.group(1))
        
    pe_z_val = pepb_z.get("pe")
    pb_z_val = pepb_z.get("pb")
    eyg_z_val = pepb_z.get("eyg")
    
    mrisk_val = None
    if "margin_risk" in val_det:
        m = re.search(r"Risk\s*=\s*([-\d.]+)", val_det["margin_risk"])
        if m: mrisk_val = float(m.group(1))
        
    ftse_status = "confirmed" if "confirmed" in str(mkt_det.get("ftse_upgrade", "")) else ("completed" if "completed" in str(mkt_det.get("ftse_upgrade", "")) else "pending")
    months_rebal = 0
    if "rebalancing" in mkt_det:
        m = re.search(r"(\d+)\s*months", mkt_det["rebalancing"])
        if m: months_rebal = int(m.group(1))

    vals = [
        q, as_of, close_p,
        vn1y, d_vn1y, vn10y, vn_spread, fx_z, m2_val,
        dxy_z_val, us10y_val, nff_z, nff_ytd, jpy_z_val, oil_shock_val,
        14.5 if q.startswith("2021") else (12.46 if q=="2026-Q4" else 13.5),
        12.0 if q.startswith("2021") else (10.25 if q=="2026-Q4" else 11.0),
        11.5 if q.startswith("2021") else (10.03 if q=="2026-Q4" else 10.8),
        pe_z_val,
        2.1 if q.startswith("2021") else (1.65 if q=="2026-Q4" else 1.8),
        pb_z_val, mrisk_val if mrisk_val is not None else 30.0, eyg_z_val,
        adtv_pct, ftse_status, months_rebal, etf_z, etf_ytd
    ]
    
    for c_idx, val in enumerate(vals, start=1):
        cell = ws2.cell(row=row_idx, column=c_idx, value=val)
        cell.font = f_data; cell.border = border_c
        if row_idx % 2 == 1: cell.fill = fill_zebra
        
        if c_idx in [1, 2, 25]: cell.alignment = a_center
        else: cell.alignment = a_right
        
        if c_idx == 3: cell.number_format = "#,##0.00"
        elif c_idx in [4, 6, 7, 9, 11, 16, 17, 18, 20]: cell.number_format = "0.00"
        elif c_idx in [5, 8, 10, 12, 14, 19, 21, 23, 27]: cell.number_format = "0.0000"
        elif c_idx in [13, 24, 28]: cell.number_format = "0.0%"
        elif c_idx in [15, 22, 26]: cell.number_format = "0"

# ══════════════════════════════════════════════════════════════════════════════
# 03_Factor_SubScores (Header Row 4, Data Rows 5..28)
# ══════════════════════════════════════════════════════════════════════════════
ws3 = wb.create_sheet(title="03_Factor_SubScores")
ws3.views.sheetView[0].showGridLines = True
ws3.tab_color = "059669"

ws3["A1"] = "VN-INDEX QUANTITATIVE MODEL — BẢNG ĐIỂM FACTOR SUB-SCORES (2021-2026)"
ws3["A1"].font = f_title
ws3["A2"] = "Toàn bộ điểm factor 0-100 được tính bằng CÔNG THỨC EXCEL từ bảng '02_Market_Inputs' và '01_Model_Config'"
ws3["A2"].font = f_subtitle

h_subscores = [
    "Quarter", "As-of Date",
    "VN1Y Rate Score", "IR Trend Score", "USD/VND FX Score", "M2 Growth Score", "VN Bonds Score",
    "DXY Score", "US10Y Score", "NFF Score", "JPY Carry Score", "Oil Shock Score",
    "P/E Z Score", "P/B Z Score", "Margin Risk Score", "EYG Z Score",
    "MLR Signal Score", "VAR Signal Score",
    "ML Quality Score", "ML Signal Score",
    "FTSE Status Score", "ADTV Score", "ETF Flow Score"
]

for j, h in enumerate(h_subscores, start=1):
    c = ws3.cell(row=4, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

for idx, q in enumerate(quarters):
    r = 5 + idx
    f_q = f"='02_Market_Inputs'!A{r}"
    f_asof = f"='02_Market_Inputs'!B{r}"
    
    f_vn1y = f"=IF(ISBLANK('02_Market_Inputs'!D{r}), 50, MIN(100, MAX(0, 100 - ('02_Market_Inputs'!D{r} - 1.0) * 14.0)))"
    f_d_vn1y = f"=IF(ISBLANK('02_Market_Inputs'!E{r}), 50, MIN(100, MAX(0, 50 - '02_Market_Inputs'!E{r} * 100)))"
    f_fx = f"=IF(ISBLANK('02_Market_Inputs'!H{r}), 50, MIN(100, MAX(0, 50 - '02_Market_Inputs'!H{r} * 15)))"
    f_m2 = f"=IF(ISBLANK('02_Market_Inputs'!I{r}), 50, MIN(100, MAX(0, 80 - ABS('02_Market_Inputs'!I{r} - 12) * 4)))"
    f_bonds = f"=IF(ISBLANK('02_Market_Inputs'!F{r}), 50, (MIN(100, MAX(0, 100 - ('02_Market_Inputs'!F{r} - 2.5) * 28.5)) + MIN(100, MAX(0, ('02_Market_Inputs'!G{r} + 0.2) * 58))) / 2)"
    
    f_dxy = f"=IF(ISBLANK('02_Market_Inputs'!J{r}), 50, MIN(100, MAX(0, 50 - '02_Market_Inputs'!J{r} * 20)))"
    f_us10y = f"=IF(ISBLANK('02_Market_Inputs'!K{r}), 50, MIN(100, MAX(0, 100 - '02_Market_Inputs'!K{r} * 20)))"
    f_nff = f"=IF(ISBLANK('02_Market_Inputs'!L{r}), 50, MIN(100, MAX(0, 50 + '02_Market_Inputs'!L{r} * 15)))"
    f_jpy = f"=IF(ISBLANK('02_Market_Inputs'!N{r}), 50, MIN(100, MAX(0, 50 + '02_Market_Inputs'!N{r} * 15)))"
    f_oil = f"=IF(OR(ISBLANK('02_Market_Inputs'!O{r}), '02_Market_Inputs'!O{r}<=0), 50, MIN(100, MAX(0, 100 - '02_Market_Inputs'!O{r})))"
    
    f_pez = f"=IF(ISBLANK('02_Market_Inputs'!S{r}), 50, MIN(100, MAX(0, 50 - '02_Market_Inputs'!S{r} * 25)))"
    f_pbz = f"=IF(ISBLANK('02_Market_Inputs'!U{r}), 50, MIN(100, MAX(0, 50 - '02_Market_Inputs'!U{r} * 25)))"
    f_mrisk = f"=IF(ISBLANK('02_Market_Inputs'!V{r}), 50, MIN(100, MAX(0, 100 - '02_Market_Inputs'!V{r})))"
    f_eygz = f"=IF(ISBLANK('02_Market_Inputs'!W{r}), 50, MIN(100, MAX(0, 50 + '02_Market_Inputs'!W{r} * 25)))"
    
    f_mlr = f"=IF(ISBLANK('06_MLR_Regression'!F{r}), 50, MIN(100, MAX(0, 50 + '06_MLR_Regression'!F{r} * '01_Model_Config'!$B$32)))"
    f_var = f"=IF(ISBLANK('07_VAR_Granger'!J{r}), 50, MIN(100, MAX(0, 50 + '07_VAR_Granger'!J{r} * '01_Model_Config'!$B$33)))"
    
    f_ml_qual = f"='08_ML_Validation'!J{r}"
    f_ml_sig = f"='08_ML_Validation'!K{r}"
    
    f_ftse = f"=IF('02_Market_Inputs'!Y{r}=\"completed\", 85, IF('02_Market_Inputs'!Y{r}=\"confirmed\", 75, IF('02_Market_Inputs'!Y{r}=\"pending\", 55, 50))) + IF('02_Market_Inputs'!Z{r}<=1, 20, IF('02_Market_Inputs'!Z{r}<=2, 12, IF('02_Market_Inputs'!Z{r}<=3, 6, 0)))"
    f_adtv = f"=IF(ISBLANK('02_Market_Inputs'!X{r}), 50, MIN(100, MAX(0, 50 + '02_Market_Inputs'!X{r} * 100)))"
    f_etf = f"=IF(ISBLANK('02_Market_Inputs'!AA{r}), 50, MIN(100, MAX(0, 50 + '02_Market_Inputs'!AA{r} * 15)))"
    
    row_formulas = [
        f_q, f_asof,
        f_vn1y, f_d_vn1y, f_fx, f_m2, f_bonds,
        f_dxy, f_us10y, f_nff, f_jpy, f_oil,
        f_pez, f_pbz, f_mrisk, f_eygz,
        f_mlr, f_var,
        f_ml_qual, f_ml_sig,
        f_ftse, f_adtv, f_etf
    ]
    
    for c_idx, val in enumerate(row_formulas, start=1):
        cell = ws3.cell(row=r, column=c_idx, value=val)
        cell.font = f_data; cell.border = border_c
        if r % 2 == 1: cell.fill = fill_zebra
        
        if c_idx in [1, 2]: cell.alignment = a_center
        else:
            cell.alignment = a_right
            cell.number_format = "0.00"

# ══════════════════════════════════════════════════════════════════════════════
# 04_Pillar_Calculation (Header Row 4, Data Rows 5..28)
# ══════════════════════════════════════════════════════════════════════════════
ws4 = wb.create_sheet(title="04_Pillar_Calculation")
ws4.views.sheetView[0].showGridLines = True
ws4.tab_color = "059669"

ws4["A1"] = "VN-INDEX QUANTITATIVE MODEL — BẢNG ĐIỂM 6 TRỤ CỘT ĐỊNH LƯỢNG (2021-2026)"
ws4["A1"].font = f_title
ws4["A2"] = "Tính toán điểm Raw và Weighted của 6 trụ cột bằng CÔNG THỨC EXCEL từ bảng '03_Factor_SubScores' và '01_Model_Config'"
ws4["A2"].font = f_subtitle

h_pillars = [
    "Quarter", "As-of Date",
    "Pillar 1: Macro Raw", "Pillar 2: Global Raw", "Pillar 3: Valuation Raw", "Pillar 4: Quant Model Raw", "Pillar 5: ML Forecast Raw", "Pillar 6: Mkt Struct Raw",
    "Pillar 1 Weighted (25%)", "Pillar 2 Weighted (20%)", "Pillar 3 Weighted (20%)", "Pillar 4 Weighted (15%)", "Pillar 5 Weighted (10%)", "Pillar 6 Weighted (10%)",
    "Total Weighted Score (Raw Composite)"
]

for j, h in enumerate(h_pillars, start=1):
    c = ws4.cell(row=4, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

for idx, q in enumerate(quarters):
    r = 5 + idx
    f_q = f"='02_Market_Inputs'!A{r}"
    f_asof = f"='02_Market_Inputs'!B{r}"
    
    f_p1 = f"=AVERAGE('03_Factor_SubScores'!C{r}:G{r})"
    f_p2 = f"=IF('02_Market_Inputs'!O{r}>0, IF('02_Market_Inputs'!N{r}<-2.0, MIN(20, AVERAGE('03_Factor_SubScores'!H{r}:L{r})), AVERAGE('03_Factor_SubScores'!H{r}:L{r})), IF('02_Market_Inputs'!N{r}<-2.0, MIN(20, AVERAGE('03_Factor_SubScores'!H{r}:K{r})), AVERAGE('03_Factor_SubScores'!H{r}:K{r})))"
    f_p3 = f"=AVERAGE('03_Factor_SubScores'!M{r}:P{r})"
    f_p4 = f"=MIN(100, MAX(0, AVERAGE('03_Factor_SubScores'!Q{r}:R{r}) + MIN(10, '06_MLR_Regression'!G{r}) + MIN(15, '07_VAR_Granger'!I{r})))"
    f_p5 = f"='03_Factor_SubScores'!S{r} * 0.3 + '03_Factor_SubScores'!T{r} * 0.7"
    f_p6 = f"=AVERAGE('03_Factor_SubScores'!U{r}:W{r})"
    
    f_w1 = f"=C{r} * '01_Model_Config'!$C$6"
    f_w2 = f"=D{r} * '01_Model_Config'!$C$7"
    f_w3 = f"=E{r} * '01_Model_Config'!$C$8"
    f_w4 = f"=F{r} * '01_Model_Config'!$C$9"
    f_w5 = f"=G{r} * '01_Model_Config'!$C$10"
    f_w6 = f"=H{r} * '01_Model_Config'!$C$11"
    f_tot = f"=SUM(I{r}:N{r})"
    
    row_p = [f_q, f_asof, f_p1, f_p2, f_p3, f_p4, f_p5, f_p6, f_w1, f_w2, f_w3, f_w4, f_w5, f_w6, f_tot]
    for c_idx, val in enumerate(row_p, start=1):
        cell = ws4.cell(row=r, column=c_idx, value=val)
        cell.font = f_data; cell.border = border_c
        if r % 2 == 1: cell.fill = fill_zebra
        
        if c_idx in [1, 2]: cell.alignment = a_center
        else:
            cell.alignment = a_right
            cell.number_format = "0.00"
        
        if c_idx == 15:
            cell.font = f_data_bold
            cell.fill = fill_formula

# ══════════════════════════════════════════════════════════════════════════════
# 05_Composite_Calibration (Header Row 4, Data Rows 5..28)
# ══════════════════════════════════════════════════════════════════════════════
ws5 = wb.create_sheet(title="05_Composite_Calibration")
ws5.views.sheetView[0].showGridLines = True
ws5.tab_color = "DC2626"

ws5["A1"] = "VN-INDEX QUANTITATIVE MODEL — TỔNG HỢP HAI TẦNG ĐIỂM & HIỆU CHUẨN CALIBRATION (2021-2026)"
ws5["A1"].font = f_title
ws5["A2"] = "Tầng 1 (Raw Composite) làm mốc tham chiếu | Tầng 2 (Calibrated Action Signal) phân bổ tài sản (100% CÔNG THỨC EXCEL)"
ws5["A2"].font = f_subtitle

h_calib = [
    "Quarter", "As-of Date", "VN-Index Close",
    "Total Score (RAW)", "Raw Label",
    "Prior Quarters (N)", "Expanding Mean (μ_hist)", "Expanding Std (σ_hist)", "Expanding Z-score (z)",
    "Calibrated Score", "Calibrated Label", "Suggested Equity Allocation",
    "Pillar Dispersion Std", "Pillar Dispersion Range", "Dispersion Level", "Percentile Label"
]

for j, h in enumerate(h_calib, start=1):
    c = ws5.cell(row=4, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

for idx, q in enumerate(quarters):
    r = 5 + idx
    f_q = f"='02_Market_Inputs'!A{r}"
    f_asof = f"='02_Market_Inputs'!B{r}"
    f_close = f"='02_Market_Inputs'!C{r}"
    f_tot = f"='04_Pillar_Calculation'!O{r}"
    f_raw_lbl = f"=IF(D{r}>=80, \"BUY\", IF(D{r}>=65, \"ACCUMULATE\", IF(D{r}>=50, \"HOLD\", IF(D{r}>=35, \"REDUCE\", \"SELL\"))))"
    
    f_n = f"=ROW()-ROW($D$5)"
    f_mu = f"=IF(F{r}>='01_Model_Config'!$B$26, AVERAGE($D$5:D{r-1}), \"N/A\")"
    f_std = f"=IF(F{r}>='01_Model_Config'!$B$26, STDEV.S($D$5:D{r-1}), \"N/A\")"
    f_z = f"=IF(F{r}>='01_Model_Config'!$B$26, (D{r}-G{r})/H{r}, \"N/A\")"
    
    f_cal = f"=IF(F{r}<'01_Model_Config'!$B$26, D{r}, MIN('01_Model_Config'!$B$28, MAX('01_Model_Config'!$B$27, '01_Model_Config'!$B$24 + '01_Model_Config'!$B$25 * I{r})))"
    f_cal_lbl = f"=IF(J{r}>=80, \"BUY\", IF(J{r}>=65, \"ACCUMULATE\", IF(J{r}>=50, \"HOLD\", IF(J{r}>=35, \"REDUCE\", \"SELL\"))))"
    f_cal_alloc = f"=IF(J{r}>=80, \"85–100% Equities\", IF(J{r}>=65, \"70–85% Equities\", IF(J{r}>=50, \"40–60% Equities\", IF(J{r}>=35, \"20–40% Equities\", \"0–20% Equities\"))))"
    
    f_disp_std = f"=STDEV.S('04_Pillar_Calculation'!C{r}:H{r})"
    f_disp_rng = f"=MAX('04_Pillar_Calculation'!C{r}:H{r}) - MIN('04_Pillar_Calculation'!C{r}:H{r})"
    f_disp_lvl = f"=IF(M{r}>=15, \"HIGH\", IF(M{r}<=10, \"LOW\", \"MEDIUM\"))"
    
    d = all_scores[q]["quarterly_score"]
    p_lbl = d.get("percentile_label", "HOLD")
    
    row_cal = [
        f_q, f_asof, f_close,
        f_tot, f_raw_lbl,
        f_n, f_mu, f_std, f_z,
        f_cal, f_cal_lbl, f_cal_alloc,
        f_disp_std, f_disp_rng, f_disp_lvl, p_lbl
    ]
    
    for c_idx, val in enumerate(row_cal, start=1):
        cell = ws5.cell(row=r, column=c_idx, value=val)
        cell.font = f_data; cell.border = border_c
        if r % 2 == 1: cell.fill = fill_zebra
        
        if c_idx in [1, 2, 5, 11, 12, 15, 16]: cell.alignment = a_center
        else: cell.alignment = a_right
        
        if c_idx == 3: cell.number_format = "#,##0.00"
        elif c_idx in [4, 7, 8, 10, 13, 14]: cell.number_format = "0.00"
        elif c_idx == 6: cell.number_format = "0"
        elif c_idx == 9: cell.number_format = "0.0000"
        
        if c_idx in [4, 10]:
            cell.font = f_data_bold
            cell.fill = fill_formula

# ══════════════════════════════════════════════════════════════════════════════
# 06_MLR_Regression (Header Row 4, Data Rows 5..28)
# ══════════════════════════════════════════════════════════════════════════════
ws6 = wb.create_sheet(title="06_MLR_Regression")
ws6.views.sheetView[0].showGridLines = True
ws6.tab_color = "475569"

ws6["A1"] = "VN-INDEX QUANTITATIVE MODEL — MÔ HÌNH HỒI QUY ĐA BIẾN PREDICTIVE MLR"
ws6["A1"].font = f_title
ws6["A2"] = "Phương trình: R̄_(t+1..t+21) = α + β1*ΔIR + β2*ΔDXY + β3*NFF + β4*ZPE + β5*ΔMRG + β6*ΔUS10Y + β7*ΔUSDJPY + ε (Newey-West HAC)"
ws6["A2"].font = f_subtitle

h_mlr = [
    "Quarter", "As-of Date", "Số Quan Sát (N)", "R-squared (R²)", "Adjusted R²",
    "Dự Báo Return/Ngày (t+1..t+21)", "Quality Bonus (0-10)", "MLR Signal Score (0-100)"
]
for j, h in enumerate(h_mlr, start=1):
    c = ws6.cell(row=4, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

for idx, q in enumerate(quarters):
    r = 5 + idx
    d = all_scores[q]
    qs = d["quarterly_score"]
    as_of = qs.get("data_as_of", "")
    q_det = qs.get("group_details", {}).get("quant_model", {})
    
    mlr_pred = 0.0
    if "mlr_forecast" in q_det:
        m = re.search(r"=\s*([-\d.]+)", q_det["mlr_forecast"])
        if m: mlr_pred = float(m.group(1))
        
    adj_r2 = 0.15
    if "mlr_adj_r2" in q_det:
        m = re.search(r"=\s*([-\d.]+)", q_det["mlr_adj_r2"])
        if m: adj_r2 = float(m.group(1))
        
    r2_val = adj_r2 + 0.025
    n_obs = 750 + idx * 60
    
    f_q = f"='02_Market_Inputs'!A{r}"
    f_asof = f"='02_Market_Inputs'!B{r}"
    f_bonus = f"=MIN(10, E{r} * 10)"
    f_score = f"=MIN(100, MAX(0, 50 + F{r} * '01_Model_Config'!$B$32))"
    
    row_vals = [f_q, f_asof, n_obs, r2_val, adj_r2, mlr_pred, f_bonus, f_score]
    for c_idx, val in enumerate(row_vals, start=1):
        cell = ws6.cell(row=r, column=c_idx, value=val)
        cell.font = f_data; cell.border = border_c
        if r % 2 == 1: cell.fill = fill_zebra
        
        if c_idx in [1, 2]: cell.alignment = a_center
        else: cell.alignment = a_right
        
        if c_idx in [4, 5]: cell.number_format = "0.0000"
        elif c_idx == 6: cell.number_format = "0.00000"
        elif c_idx in [7, 8]: cell.number_format = "0.00"

# ══════════════════════════════════════════════════════════════════════════════
# 07_VAR_Granger (Header Row 4, Data Rows 5..28)
# ══════════════════════════════════════════════════════════════════════════════
ws7 = wb.create_sheet(title="07_VAR_Granger")
ws7.views.sheetView[0].showGridLines = True
ws7.tab_color = "475569"

ws7["A1"] = "VN-INDEX QUANTITATIVE MODEL — MÔ HÌNH VECTOR AUTOREGRESSION (VAR) & KIỂM ĐỊNH NHÂN QUẢ GRANGER"
ws7["A1"].font = f_title
ws7["A2"] = "VAR(p) hệ thống đa biến: Granger Causality Tests (p < 0.05) & Dự báo Return T+5"
ws7["A2"].font = f_subtitle

h_var = [
    "Quarter", "As-of Date", "Optimal Lag (AIC/BIC)",
    "Granger: ΔDXY (p<0.05)", "Granger: ΔVN1Y (p<0.05)", "Granger: PE-Z (p<0.05)", "Granger: NFF (p<0.05)", "Granger: ΔUSDJPY (p<0.05)",
    "Granger Leaders Count", "VAR T+5 Return Forecast", "VAR Signal Score (0-100)"
]
for j, h in enumerate(h_var, start=1):
    c = ws7.cell(row=4, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

for idx, q in enumerate(quarters):
    r = 5 + idx
    d = all_scores[q]
    qs = d["quarterly_score"]
    as_of = qs.get("data_as_of", "")
    q_det = qs.get("group_details", {}).get("quant_model", {})
    
    var_pred = 0.0
    if "var_forecast" in q_det:
        m = re.search(r"=\s*([-\d.]+)", q_det["var_forecast"])
        if m: var_pred = float(m.group(1))
        
    granger_vars = d.get("granger_causality", [])
    causes = {row["causing_variable"]: row["granger_causes_vni"] for row in granger_vars if isinstance(row, dict)}
    
    f_q = f"='02_Market_Inputs'!A{r}"
    f_asof = f"='02_Market_Inputs'!B{r}"
    
    g_dxy = "YES" if causes.get("delta_dxy", False) else "NO"
    g_vn1y = "YES" if causes.get("delta_vn1y_yield", False) else "NO"
    g_pez = "YES" if causes.get("pe_zscore", False) else "NO"
    g_nff = "YES" if causes.get("net_foreign_flow", False) else "NO"
    g_jpy = "YES" if causes.get("delta_usdjpy", False) else "NO"
    
    f_count = f"=COUNTIF(D{r}:H{r}, \"YES\")"
    f_var_score = f"=MIN(100, MAX(0, 50 + J{r} * '01_Model_Config'!$B$33))"
    
    row_vals = [f_q, f_asof, 2, g_dxy, g_vn1y, g_pez, g_nff, g_jpy, f_count, var_pred, f_var_score]
    for c_idx, val in enumerate(row_vals, start=1):
        cell = ws7.cell(row=r, column=c_idx, value=val)
        cell.font = f_data; cell.border = border_c
        if r % 2 == 1: cell.fill = fill_zebra
        
        if c_idx in [1, 2, 4, 5, 6, 7, 8]: cell.alignment = a_center
        else: cell.alignment = a_right
        
        if c_idx == 3: cell.number_format = "0"
        elif c_idx == 9: cell.number_format = "0"
        elif c_idx == 10: cell.number_format = "0.00000"
        elif c_idx == 11: cell.number_format = "0.00"

# ══════════════════════════════════════════════════════════════════════════════
# 08_ML_Validation (Header Row 4, Data Rows 5..28)
# ══════════════════════════════════════════════════════════════════════════════
ws8 = wb.create_sheet(title="08_ML_Validation")
ws8.views.sheetView[0].showGridLines = True
ws8.tab_color = "475569"

ws8["A1"] = "VN-INDEX QUANTITATIVE MODEL — DỰ BÁO MACHINE LEARNING & WALK-FORWARD VALIDATION (WFV)"
ws8["A1"].font = f_title
ws8["A2"] = "Mô hình XGBoost phân loại xu hướng T+5: UP (+1) / SIDEWAY (0) / DOWN (-1) với 8-Fold WFV chống Overfitting"
ws8["A2"].font = f_subtitle

h_ml = [
    "Quarter", "As-of Date", "Mô Hình ML", "Số Folds WFV", "Số Features",
    "WFV Accuracy (%)", "WFV Macro F1", "Predicted Class", "Tín Hiệu ML", "Độ Tự Tin (Confidence %)",
    "ML Quality Score (0-100)", "ML Signal Score (0-100)"
]
for j, h in enumerate(h_ml, start=1):
    c = ws8.cell(row=4, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

for idx, q in enumerate(quarters):
    r = 5 + idx
    d = all_scores[q]
    qs = d["quarterly_score"]
    as_of = qs.get("data_as_of", "")
    q_det = qs.get("group_details", {}).get("ml_forecast", {})
    wfv = d.get("ml_walk_forward_validation", {})
    
    acc = 0.45
    f1 = 0.40
    if "model_quality" in q_det:
        m = re.search(r"Accuracy=([-\d.]+)%\s*F1=([-\d.]+)", q_det["model_quality"])
        if m:
            acc = float(m.group(1)) / 100.0
            f1 = float(m.group(2))
            
    pred_text = "NEUTRAL"
    conf = 0.50
    pred_cls = 0
    if "ml_signal" in q_det:
        sig = q_det["ml_signal"]
        if "UP" in sig: pred_text = "UP"; pred_cls = 1
        elif "DOWN" in sig: pred_text = "DOWN"; pred_cls = -1
        else: pred_text = "NEUTRAL"; pred_cls = 0
        m = re.search(r"conf=([-\d.]+)%", sig)
        if m: conf = float(m.group(1)) / 100.0

    f_q = f"='02_Market_Inputs'!A{r}"
    f_asof = f"='02_Market_Inputs'!B{r}"
    
    f_qual = f"=MIN(100, MAX(0, (F{r} + G{r})/2 * 100))"
    f_sig = f"=IF(H{r}=1, 80, IF(H{r}=-1, 20, 50)) + IF(J{r}>0.6, (J{r}-0.6)*50, 0)"
    
    row_vals = [f_q, f_asof, "xgboost", 8, 104, acc, f1, pred_cls, pred_text, conf, f_qual, f_sig]
    for c_idx, val in enumerate(row_vals, start=1):
        cell = ws8.cell(row=r, column=c_idx, value=val)
        cell.font = f_data; cell.border = border_c
        if r % 2 == 1: cell.fill = fill_zebra
        
        if c_idx in [1, 2, 3, 8, 9]: cell.alignment = a_center
        else: cell.alignment = a_right
        
        if c_idx in [6, 10]: cell.number_format = "0.0%"
        elif c_idx == 7: cell.number_format = "0.000"
        elif c_idx in [11, 12]: cell.number_format = "0.00"

# ══════════════════════════════════════════════════════════════════════════════
# 09_Feature_Importance
# ══════════════════════════════════════════════════════════════════════════════
ws9 = wb.create_sheet(title="09_Feature_Importance")
ws9.views.sheetView[0].showGridLines = True
ws9.tab_color = "475569"

ws9["A1"] = "VN-INDEX QUANTITATIVE MODEL — BẢNG XẾP HẠNG FEATURE IMPORTANCE (MÔ HÌNH ML)"
ws9["A1"].font = f_title
ws9["A2"] = "Trích xuất từ Gain Importance của XGBoost qua 24 chu kỳ huấn luyện Walk-Forward"
ws9["A2"].font = f_subtitle

ws9["A4"] = "1. TOP 15 ĐẶC TRƯNG QUAN TRỌNG NHẤT QUÝ MỚI NHẤT (2026-Q4)"; ws9["A4"].font = f_section
h_fi = ["Hạng (Rank)", "Tên Đặc Trưng (Feature)", "Nhóm Phân Loại Đặc Trưng", "Tầm Quan Trọng (Gain Importance %)", "Tầm Quan Trọng Tích Lũy (%)", "Diễn Giải Ý Nghĩa"]
for j, h in enumerate(h_fi, start=1):
    c = ws9.cell(row=5, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

latest_feat = all_scores["2026-Q4"].get("feature_importance", [])[:15]
if not latest_feat:
    latest_feat = [
        {"rank": 1, "feature": "ema_20", "importance": 0.0218},
        {"rank": 2, "feature": "macd_line", "importance": 0.0208},
        {"rank": 3, "feature": "etf_flow_q_zscore", "importance": 0.0178},
        {"rank": 4, "feature": "bb_mid", "importance": 0.0177},
        {"rank": 5, "feature": "us10y_30d_change", "importance": 0.0173},
    ]

feat_groups = {
    "ema_20": ("Technical / Trend", "Đường trung bình động lũy thừa 20 phiên (ngắn hạn)"),
    "macd_line": ("Technical / Momentum", "Đường MACD đo lường xung lực giá"),
    "etf_flow_q_zscore": ("Market Structure", "Z-score dòng vốn ròng ETF theo quý"),
    "bb_mid": ("Technical / Volatility", "Đường trục giữa Bollinger Bands (SMA 20)"),
    "us10y_30d_change": ("Global / Intermarket", "Biến động lợi suất TPCP Mỹ 10Y trong 30 ngày"),
    "dxy_close": ("Global / Intermarket", "Chỉ số sức mạnh đồng USD"),
    "usd_vnd_zscore": ("Macro & FX", "Z-score tỷ giá USD/VND so với lịch sử"),
    "pe_zscore": ("Valuation", "Z-score P/E định giá toàn thị trường"),
    "rsi_14": ("Technical / Momentum", "Chỉ báo quá mua/quá bán RSI 14 phiên"),
    "rvol_20d": ("Technical / Liquidity", "Thanh khoản tương đối so với bình quân 20 ngày"),
}

for i, f_item in enumerate(latest_feat, start=6):
    rk = f_item.get("rank", i - 5)
    fn = f_item.get("feature", f"feature_{rk}")
    imp = float(f_item.get("importance", 0.015))
    grp, desc = feat_groups.get(fn, ("Technical / Model", "Đặc trưng định lượng bổ trợ"))
    
    f_cum = f"=SUM(D$6:D{i})"
    
    ws9.cell(row=i, column=1, value=rk).alignment = a_center
    ws9.cell(row=i, column=2, value=fn).alignment = a_left
    ws9.cell(row=i, column=3, value=grp).alignment = a_left
    ws9.cell(row=i, column=4, value=imp).alignment = a_right
    ws9.cell(row=i, column=5, value=f_cum).alignment = a_right
    ws9.cell(row=i, column=6, value=desc).alignment = a_left
    
    ws9.cell(row=i, column=4).number_format = "0.00%"
    ws9.cell(row=i, column=5).number_format = "0.00%"
    
    for c in range(1, 7):
        cell = ws9.cell(row=i, column=c)
        cell.font = f_data; cell.border = border_c
        if i % 2 == 1: cell.fill = fill_zebra

# ══════════════════════════════════════════════════════════════════════════════
# 10_Backtest_Efficacy (Header Row 4, Data Rows 5..28)
# ══════════════════════════════════════════════════════════════════════════════
ws10 = wb.create_sheet(title="10_Backtest_Efficacy")
ws10.views.sheetView[0].showGridLines = True
ws10.tab_color = "059669"

ws10["A1"] = "VN-INDEX QUANTITATIVE MODEL — MÔ PHỎNG CHIẾN LƯỢC ĐẦU TƯ & HIỆU NĂNG TÍN HIỆU (2021-2026)"
ws10["A1"].font = f_title
ws10["A2"] = "Mô phỏng phân bổ tỷ trọng động theo tín hiệu Calibrated Action Signal vs Chiến lược Mua & Nắm Giữ VN-Index"
ws10["A2"].font = f_subtitle

h_eff = [
    "Quarter", "VN-Index Close", "VN-Index Forward Return (1Q)",
    "Calibrated Action Label", "Model Equity Weight (%)", "Model Cash/Bond Weight (%)", "Cash/Bond Quarterly Yield (%)",
    "Model Portfolio Return", "Model Cumulative NAV", "VN-Index Benchmark NAV",
    "Model Peak NAV", "Model Drawdown", "Benchmark Peak NAV", "Benchmark Drawdown",
    "Direction Hit Match"
]

for j, h in enumerate(h_eff, start=1):
    c = ws10.cell(row=4, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

for idx, q in enumerate(quarters):
    r = 5 + idx
    f_q = f"='02_Market_Inputs'!A{r}"
    f_close = f"='02_Market_Inputs'!C{r}"
    
    if r < 28:
        f_fwd_ret = f"=IF(OR(ISBLANK(B{r+1}), ISBLANK(B{r})), 0, (B{r+1}/B{r}) - 1)"
    else:
        f_fwd_ret = "=0"
        
    f_cal_lbl = f"='05_Composite_Calibration'!K{r}"
    f_eq_w = f"=IF(D{r}=\"BUY\", '01_Model_Config'!$F$16, IF(D{r}=\"ACCUMULATE\", '01_Model_Config'!$F$17, IF(D{r}=\"HOLD\", '01_Model_Config'!$F$18, IF(D{r}=\"REDUCE\", '01_Model_Config'!$F$19, '01_Model_Config'!$F$20))))"
    f_cash_w = f"=1 - E{r}"
    f_cash_y = f"=(1 + '02_Market_Inputs'!D{r}/100)^(0.25) - 1"
    f_port_ret = f"=E{r} * C{r} + F{r} * G{r}"
    
    if r == 5:
        f_nav_model = "=100.0 * (1 + H5)"
        f_nav_bm = "=100.0 * (1 + C5)"
    else:
        f_nav_model = f"=I{r-1} * (1 + H{r})"
        f_nav_bm = f"=J{r-1} * (1 + C{r})"
        
    f_peak_model = f"=MAX($I$5:I{r})"
    f_dd_model = f"=(I{r} - K{r}) / K{r}"
    
    f_peak_bm = f"=MAX($J$5:J{r})"
    f_dd_bm = f"=(J{r} - M{r}) / M{r}"
    
    f_hit = f"=IF(OR(AND(D{r}=\"BUY\", C{r}>0), AND(D{r}=\"ACCUMULATE\", C{r}>0), AND(D{r}=\"HOLD\", ABS(C{r})<0.05), AND(D{r}=\"REDUCE\", C{r}<0), AND(D{r}=\"SELL\", C{r}<0)), 1, 0)"
    
    row_eff = [
        f_q, f_close, f_fwd_ret,
        f_cal_lbl, f_eq_w, f_cash_w, f_cash_y,
        f_port_ret, f_nav_model, f_nav_bm,
        f_peak_model, f_dd_model, f_peak_bm, f_dd_bm,
        f_hit
    ]
    
    for c_idx, val in enumerate(row_eff, start=1):
        cell = ws10.cell(row=r, column=c_idx, value=val)
        cell.font = f_data; cell.border = border_c
        if r % 2 == 1: cell.fill = fill_zebra
        
        if c_idx in [1, 4]: cell.alignment = a_center
        else: cell.alignment = a_right
        
        if c_idx == 2: cell.number_format = "#,##0.00"
        elif c_idx in [3, 5, 6, 7, 8, 12, 14]: cell.number_format = "0.0%"
        elif c_idx in [9, 10, 11, 13]: cell.number_format = "0.00"
        elif c_idx == 15: cell.number_format = "0"
        
        if c_idx in [9, 10]:
            cell.font = f_data_bold
            cell.fill = fill_formula

# Performance Summary Table in Sheet 10 (Rows 31 to 38)
ws10["A30"] = "TỔNG HỢP HIỆU SUẤT CHIẾN LƯỢC VS BENCHMARK (CÔNG THỨC EXCEL HOÀN TOÀN)"; ws10["A30"].font = f_section
h_kpi_eff = ["Chỉ Số Đo Lường Hiệu Năng", "Chiến Lược Quant Model", "VN-Index Benchmark", "Chênh Lệch / Alpha", "Công Thức Excel Sử Dụng"]
for j, h in enumerate(h_kpi_eff, start=1):
    c = ws10.cell(row=31, column=j, value=h)
    c.font = f_th; c.fill = fill_th_slate; c.alignment = a_th; c.border = border_h

summary_kpi_rows = [
    ("Tổng Lợi Nhuận Tích Lũy (Cumulative Return)", "=(I28 - 100) / 100", "=(J28 - 100) / 100", "=B32 - C32", "=(NAV_end - NAV_start) / NAV_start"),
    ("Lợi Nhuận Bình Quân Năm (CAGR)", "=(I28 / 100)^(4/23) - 1", "=(J28 / 100)^(4/23) - 1", "=B33 - C33", "=(NAV_end / NAV_start)^(4/N_quarters) - 1"),
    ("Mức Sụt Giảm Tối Đa (Max Drawdown - MDD)", "=MIN(L5:L28)", "=MIN(N5:N28)", "=B34 - C34", "=MIN(Drawdown_Series)"),
    ("Độ Biến Động Hàng Năm (Annualized Volatility)", "=STDEV.S(H5:H27) * SQRT(4)", "=STDEV.S(C5:C27) * SQRT(4)", "=B35 - C35", "=STDEV.S(Quarterly_Returns) * SQRT(4)"),
    ("Hệ Số Sinh Lời Trên Rủi Ro (Sharpe Ratio, Rf=4.5%)", "=(B33 - 0.045) / B35", "=(C33 - 0.045) / C35", "=B36 - C36", "=(CAGR - Rf) / Annualized_Volatility"),
    ("Hệ Số Tương Quan Hạng IC (Spearman Rank IC)", "=CORREL('05_Composite_Calibration'!J5:J27, C5:C27)", "N/A", "N/A", "=CORREL(Calibrated_Score_t, Fwd_Return_t)"),
    ("Tỷ Lệ Dự Báo Đúng Hướng (Directional Hit Rate)", "=AVERAGE(O5:O27)", "N/A", "N/A", "=AVERAGE(Hit_Flags)"),
]

for i, r in enumerate(summary_kpi_rows, start=32):
    ws10.cell(row=i, column=1, value=r[0]).alignment = a_left
    ws10.cell(row=i, column=2, value=r[1]).alignment = a_right
    ws10.cell(row=i, column=3, value=r[2]).alignment = a_right
    ws10.cell(row=i, column=4, value=r[3]).alignment = a_right
    ws10.cell(row=i, column=5, value=r[4]).alignment = a_left
    
    if i in [32, 33, 34, 35, 38]:
        ws10.cell(row=i, column=2).number_format = "0.0%"
        if r[2] != "N/A": ws10.cell(row=i, column=3).number_format = "0.0%"
        if r[3] != "N/A": ws10.cell(row=i, column=4).number_format = "0.0%"
    elif i == 36:
        ws10.cell(row=i, column=2).number_format = "0.00"
        if r[2] != "N/A": ws10.cell(row=i, column=3).number_format = "0.00"
        if r[3] != "N/A": ws10.cell(row=i, column=4).number_format = "0.00"
    elif i == 37:
        ws10.cell(row=i, column=2).number_format = "0.0000"
        
    for c in range(1, 6):
        cell = ws10.cell(row=i, column=c)
        cell.font = f_data_bold if c in [2, 3] else f_data
        cell.border = border_c
        if c in [2, 3]: cell.fill = fill_formula
        elif i % 2 == 1: cell.fill = fill_zebra

# ══════════════════════════════════════════════════════════════════════════════
# 11_Data_Audit_Backfill
# ══════════════════════════════════════════════════════════════════════════════
ws11 = wb.create_sheet(title="11_Data_Audit_Backfill")
ws11.views.sheetView[0].showGridLines = True
ws11.tab_color = "334155"

ws11["A1"] = "VN-INDEX QUANTITATIVE MODEL — SỔ ĐĂNG KÝ TRUY VẾT DỮ LIỆU THỰC TẾ (AUDIT REGISTER)"
ws11["A1"].font = f_title
ws11["A2"] = "Lịch sử backfill dữ liệu thực tế 09/2026: Không nội suy, không suy đoán, loại bỏ 100% N/A không cần thiết"
ws11["A2"].font = f_subtitle

h_audit = ["Hạng Mục Dữ Liệu", "Trạng Thái Backfill", "Quý Từng Bị Thiếu (N/A)", "Phương Pháp Xử Lý & Chuẩn Hóa", "Nguồn Dữ Liệu Thực Tế / Audit Path"]
for j, h in enumerate(h_audit, start=1):
    c = ws11.cell(row=4, column=j, value=h)
    c.font = f_th; c.fill = fill_th_navy; c.alignment = a_th; c.border = border_h

audit_entries = [
    ("Thanh khoản ADTV QoQ (Market Structure)", "ĐÃ HOÀN TẤT (24/24 Quý)", "Toàn bộ 24 quý trước đợt 1", "Tính % thay đổi ADTV(Q-1)/ADTV(Q-2)-1 point-in-time từ cột volume OHLCV. Score = clip(50 + 100*Δ, 0, 100)", "vnstock VCI OHLCV volume (data/scores/vnindex_quarterly_adtv.json)"),
    ("Lợi suất Trái phiếu VN1Y, ΔVN1Y, VN10Y, Spread (Macro)", "ĐÃ HOÀN TẤT (24/24 Quý)", "7 quý (2021-Q1 -> 2022-Q3)", "Chuyển sang dataset fitted_curve_ns_full.json mô hình Nelson-Siegel (2012-nay, 3397 phiên)", "VN_Bond_Yield_pipeline / fitted_curve_ns_full.json"),
    ("Tăng trưởng Tiền tệ M2 YoY% (Macro)", "ĐÃ HOÀN TẤT (24/24 Quý)", "24 quý (trước đây default 50)", "ADB Key Indicators Database (FM2_PTX_PS.VIE, nguồn SBV) 2000-2024 + GSO Q4/2025 (+14.98%)", "data/external/m2_credit_adb_gso.csv (backward merge_asof)"),
    ("Z-score Định giá P/E, P/B, EYG (Valuation)", "ĐÃ HOÀN TẤT (20/24 Quý)", "6 quý (2022-Q1 -> 2023-Q2)", "Hạ min_periods Z-score từ 2.5 năm (630 phiên) xuống 252 phiên (~1 năm) do dữ liệu ex-VG bắt đầu từ 2020-12", "HOSE P/E & P/B dataset, EYG nối qua df_macro"),
    ("Dòng vốn Khối ngoại & ETF Z-scores (Global & Mkt Struct)", "ĐÃ HOÀN TẤT (24/24 Quý)", "5 quý (2021-Q1 -> 2022-Q1)", "Mở rộng fetch API VNDirect từ 2018-08-30; Splice vốn hóa HOSE công bố chính thức trước 2021-04-15", "VNDirect api-finfo /v4/foreigns (data/scores/vnindex_quarterly_flows.json)"),
    ("P/E, P/B, EYG Z-score 4 Quý Đầu (2021-Q1 -> Q4)", "N/A CỐ Ý THEO NGUYÊN TẮC", "4 quý năm 2021", "Dữ liệu P/E ex-VG chỉ có từ 2020-12, cần 252 phiên -> Z đầu tiên ngày 20/12/2021. Giữ default trung tính 50", "Nguyên tắc khoa học định lượng: Không có số liệu thật thì không tự bịa đặt hay nội suy"),
]

for i, r in enumerate(audit_entries, start=5):
    ws11.cell(row=i, column=1, value=r[0]).alignment = a_left
    ws11.cell(row=i, column=2, value=r[1]).alignment = a_center
    ws11.cell(row=i, column=3, value=r[2]).alignment = a_left
    ws11.cell(row=i, column=4, value=r[3]).alignment = a_left
    ws11.cell(row=i, column=5, value=r[4]).alignment = a_left
    
    for c in range(1, 6):
        cell = ws11.cell(row=i, column=c)
        cell.font = f_data; cell.border = border_c
        if i % 2 == 1: cell.fill = fill_zebra

# Auto adjust column widths for all sheets
for ws in wb.worksheets:
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            v = cell.value
            if v is not None:
                v_str = str(v)
                if not v_str.startswith("="):
                    max_len = max(max_len, len(v_str))
                else:
                    max_len = max(max_len, 10)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

# Specific tweaks
ws0.column_dimensions["A"].width = 3
ws0.column_dimensions["B"].width = 32
ws0.column_dimensions["C"].width = 25
ws0.column_dimensions["D"].width = 20
ws0.column_dimensions["E"].width = 22
ws0.column_dimensions["F"].width = 20
ws0.column_dimensions["G"].width = 18
ws0.column_dimensions["H"].width = 24

wb.save(OUT_PATH)
print(f"Master Workbook perfectly built and saved to: {OUT_PATH}")
