"""
generate_excel_report.py — Xuất Workbook Excel Phân tích Định lượng.

Đọc output/exports/score_*.json + lịch sử điểm + giá VN-Index theo quý,
tạo file Excel đa sheet (factor impact, Granger, ML validation,
signal-efficacy backtest...) như một hệ thống quant finance thực thụ.

Chạy:  python scripts/generate_excel_report.py
"""

import logging
import os
import sys

sys.path.append(os.getcwd())

from src.reporting.excel_builder import build_excel_report

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

if __name__ == "__main__":
    path = build_excel_report()
    print(f"Excel workbook written -> {path}")
