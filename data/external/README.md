# data/external — Dữ liệu nguồn committed (không phải dữ liệu sinh ra bởi pipeline)

## m2_credit_adb_gso.csv

Cung tiền M2 (YoY, %) và tăng trưởng tín dụng (YoY, %) của Việt Nam — quan sát
**cuối năm**, dùng làm fallback offline cho `fetch_m2_credit_auto()`
(`src/data/fetcher.py`).

### Nguồn từng cột

- **`m2_yoy_pct` 2015–2024**: ADB Key Indicators Database, SDMX dataflow
  `DF_MF_MON`, indicator `FM2_PTX_PS` *"Money supply (% annual change)"*,
  economy `VIE`. Nguồn gốc số liệu theo ADB: **State Bank of Viet Nam**.
  API: `https://kidb.adb.org/api/v5/sdmx/data/ADB,DF_MF_MON/A.FM2_PTX_PS.VIE?format=sdmx-json`
  (fetch & đối chiếu ngày 2026-09-28; giá trị làm tròn 2 chữ số thập phân).
- **`m2_yoy_pct` 2025 = 14.98**: GSO — Báo cáo tình hình kinh tế - xã hội quý IV/2025:
  *"Tổng phương tiện thanh toán đến ngày 22/12/2025 tăng 14,98% so với cuối năm 2024"*.
  (`tapchinganhang.gov.vn` đăng lại bản cáohtinh GSO, 2026).
- **`credit_growth_yoy_pct` 2024 = 15.08**: GSO — tín dụng toàn nền kinh tế năm 2024.
- **`credit_growth_yoy_pct` 2025 = 17.65**: GSO — tín dụng đến 22/12/2025
  (cùng báo cáo quý IV/2025 như trên).
- **`m2_b_vnd`**: để trống — chưa có chuỗi mức (tỷ VND) kiểm chứng được;
  KHÔNG điền suy đoán.

### Nguyên tắc point-in-time

Mỗi dòng là giá trị YoY **đo tại** ngày `date`. Khi chấm điểm quý Q (as-of cuối
quý Q−1), `build_macro_features` dùng `merge_asof(direction="backward")` —
quyết định Q/2021 nhận M2 năm 2020, Q/2022 nhận năm 2021, …

### 2026 — KHÔNG có số liệu & giữ N/A

Đến 28/09/2026, GSO/SBV **chưa công bố** M2 YoY cho bất kỳ tháng nào của 2026
(đầu 2026 chỉ có mức ~19,6 triệu tỷ, +0,69% so với đầu năm — là mức tăng tuyệt
đối, không phải YoY, không dùng được). Không bịa số → các quý 2026 dùng giá trị
2025 theo as-of backward, đúng logic "số đã công bố gần nhất".
