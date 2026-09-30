# VN-Index Quantitative Model Explanation / Giải thích Mô hình Định lượng VN-Index

## 1. [EN] Purpose / [VN] Mục đích

[EN] This model produces a quarterly allocation-regime score and action. It is NOT a return forecast and is not a crash probability.

[VN] Mô hình tạo điểm thế trận phân bổ và hành động theo quý. Đây KHÔNG phải dự báo lợi suất và không phải xác suất sụp đổ.

## 2. [EN] Method / [VN] Phương pháp

[EN] The published calibration method is `winsorized_expanding_zscore_v2`. For 2026-Q4, the raw score is 47.67 (REDUCE) and the calibrated score is 33.97 (SELL); the historical standard-deviation floor was applied: no. Inputs are point-in-time and publication stops if a required source fails.

[VN] Phương pháp hiệu chỉnh đã công bố là `winsorized_expanding_zscore_v2`. Với 2026-Q4, điểm thô là 47.67 (REDUCE) và điểm hiệu chỉnh là 33.97 (SELL); sàn độ lệch chuẩn lịch sử được áp dụng: no. Dữ liệu tuân thủ point-in-time và việc công bố dừng nếu nguồn bắt buộc gặp lỗi.

## 3. [EN] Limitations / [VN] Hạn chế

[EN] The evidence set contains 24 published quarters, so uncertainty is wide. Weights, thresholds, and calibration parameters reflect design judgment informed by the full sample and were not optimized out of sample. The latest observation is PROVISIONAL as of 2026-09-25.

[VN] Tập bằng chứng gồm 24 quý đã công bố nên khoảng bất định rộng. Trọng số, ngưỡng và tham số hiệu chỉnh phản ánh phán định thiết kế khi đã biết toàn mẫu, chưa được tối ưu ngoài mẫu. Quan sát mới nhất ở trạng thái PROVISIONAL tại ngày 2026-09-25.

## 4. [EN] Delivery files / [VN] Danh mục bàn giao

[EN] The delivery comprises the official formula-driven Architecture workbook, a values-baked viewer twin, and this bilingual report in Markdown and DOCX. The formula workbook is the primary audit document.

[VN] Gói bàn giao gồm workbook Architecture chạy bằng công thức, bản sinh đôi đã bake giá trị cho trình xem nhanh, và báo cáo song ngữ này ở định dạng Markdown và DOCX. Workbook công thức là tài liệu kiểm toán chính thức.

## [EN/VN] Published quarterly record / Lịch sử quý đã công bố

| Quarter | As-of | Raw | Raw label | Calibrated | Action | Status |
|---|---|---:|---|---:|---|---|
| 2021-Q1 | 2020-12-31 | 66.86 | ACCUMULATE | 66.86 | ACCUMULATE | FINAL |
| 2021-Q2 | 2021-03-31 | 62.75 | HOLD | 62.75 | HOLD | FINAL |
| 2021-Q3 | 2021-06-30 | 63.44 | HOLD | 63.44 | HOLD | FINAL |
| 2021-Q4 | 2021-09-30 | 60.22 | HOLD | 60.22 | HOLD | FINAL |
| 2022-Q1 | 2021-12-31 | 59.69 | HOLD | 39.12 | REDUCE | FINAL |
| 2022-Q2 | 2022-03-31 | 51.25 | HOLD | 26.25 | SELL | FINAL |
| 2022-Q3 | 2022-06-30 | 57.52 | HOLD | 40.99 | REDUCE | FINAL |
| 2022-Q4 | 2022-09-30 | 45.88 | REDUCE | 20.88 | SELL | FINAL |
| 2023-Q1 | 2022-12-30 | 58.49 | HOLD | 50.08 | HOLD | FINAL |
| 2023-Q2 | 2023-03-31 | 57.35 | HOLD | 47.42 | REDUCE | FINAL |
| 2023-Q3 | 2023-06-30 | 56.64 | HOLD | 45.78 | REDUCE | FINAL |
| 2023-Q4 | 2023-09-29 | 50.28 | HOLD | 29.45 | SELL | FINAL |
| 2024-Q1 | 2023-12-29 | 47.02 | REDUCE | 23.54 | SELL | FINAL |
| 2024-Q2 | 2024-03-29 | 53.70 | HOLD | 42.92 | REDUCE | FINAL |
| 2024-Q3 | 2024-06-28 | 49.74 | REDUCE | 33.65 | SELL | FINAL |
| 2024-Q4 | 2024-09-30 | 53.13 | HOLD | 42.96 | REDUCE | FINAL |
| 2025-Q1 | 2024-12-31 | 49.61 | REDUCE | 34.51 | SELL | FINAL |
| 2025-Q2 | 2025-03-31 | 51.03 | HOLD | 38.94 | REDUCE | FINAL |
| 2025-Q3 | 2025-06-30 | 55.20 | HOLD | 49.86 | REDUCE | FINAL |
| 2025-Q4 | 2025-09-30 | 51.98 | HOLD | 41.55 | REDUCE | FINAL |
| 2026-Q1 | 2025-12-31 | 51.47 | HOLD | 40.48 | REDUCE | FINAL |
| 2026-Q2 | 2026-03-31 | 44.38 | REDUCE | 21.85 | SELL | FINAL |
| 2026-Q3 | 2026-06-30 | 46.59 | REDUCE | 30.12 | SELL | FINAL |
| 2026-Q4 | 2026-09-25 | 47.67 | REDUCE | 33.97 | SELL | PROVISIONAL |
