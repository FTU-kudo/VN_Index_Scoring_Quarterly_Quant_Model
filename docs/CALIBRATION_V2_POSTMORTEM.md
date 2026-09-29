# Calibration v2 Postmortem — Sự cố 2022-Q2 calibrated = 0.00/SELL (fix sau PR #8)

> **Phạm vi:** tầng 2 của scoring — *calibrated action score* (điểm hành động hiệu chuẩn).
> Raw composite (tầng 1) và các forecast layer (XGBoost/VAR t+5, MLR ~1 tháng) **không đổi**.
> Ngày viết: 2026-09-29 · Branch: `arena/01a0edcf-vn-index-scoring-quarterly-qua`

---

## 1. Triệu chứng

Sau khi merge PR #8 (commit `6f4ef0c`), artifact production cho **2022-Q2** là:

| Trường | Giá trị |
|---|---|
| `total_score` (raw composite, PIT) | **51.25 / 100** — bối cảnh factor trung tính |
| `calibrated_score` (hành động) | **0.00 / 100 → SELL (0% cơ sở ngành tài chính, 100% tiền mặt)** |

Một raw score gần như neutral (51.25) bị biến thành tín hiệu hành động cực đoan nhất có thể (0.00). Đây là **lỗi toán học của tầng calibration**, không phải do dữ liệu factor.

## 2. Root cause

Hàm `calibrate_total_score()` (v1) chuẩn hoá raw score theo lịch sử mở rộng (expanding window, chỉ các quý TRƯỚC đó):

```
z = (raw − μ_hist) / σ_hist ;  calibrated = clip(50 + 15·z, 0, 100)
```

Tại 2022-Q2, lịch sử 5 quý trước [66.86, 62.75, 63.44, 60.22, 59.69] có **σ quan sát rất nhỏ (≈ 2.87 điểm)** — đó là nhiễu lấy mẫu của 5 điểm dữ liệu, không phải bằng chứng rằng thị trường "ổn định đến mức 2.8 điểm = 1σ tự nhiên". Kết quả:

```
z = (51.25 − 62.59) / 2.87 ≈ −3.95  →  50 + 15×(−3.95) = −9.3  →  clip về 0.00
```

**Ba khuyếm khuyết nằm ở công thức, không nằm ở dữ liệu:**

1. **Không có sàn cho σ** — khi lịch sử hẹp (ít quý, raw biến động nhỏ), σ mẫu ước lượng sai dispersion thật → tín hiệu vừa phải bị thổi phồng thành cực đoan.
2. **Không winsorise z** — |z| lớn từ σ nhiễu được map tuyến tính vào tín hiệu hành động mà không có ngưỡng "điểm tin bền vững" (bounded-evidence).
3. **Không có guardrail so với raw** — calibrated được phép trôi xa raw composite tới mức mất nghĩa cinh quyền (51.25 → 0), vi phạm điều kiện định tính "raw ≈ 50 không được tự động thành 0".

Lưu ý trung thực: **hướng tín hiệu SELL tại 2022-Q2 là hợp lý** (2021-H2 raw liên tục xấu đi, và thực tế VN-Index giảm ~19.7% trong Q2-2022) — lỗi duy nhất là **độ lớn cực đoan (0.00) và semantics bị bóp méo**.

## 3. So sánh các phương án (đánh giá bằng code/harness, không chọn theo "đẹp số")

Mỗi phương án được chạy trên toàn bộ 24 quý thật (raw series từ parquet, expanding window, chỉ quý trước), đối chiếu các tiêu chí: không tự động về 0 khi raw≈50; 0/100 chỉ khi bằng chứng mạnh+ổn định; monotone; PIT; dễ kiểm chứng forward-return; ít tham số.

| Phương án | Bản chất | Ứng xử 2022-Q2 | Nhược điểm chính | Kết luận |
|---|---|---|---|---|
| **A. Giữ nguyên z-score v1** | `clip(50+15z,0,100)` | 0.00 — chính là lỗi | Không chống được σ nhiễu; 0/100 đạt được quá dễ | ❌ |
| **B. Winsorised z (cap \|z\| ≤ 3)** | như A + kẹp z | ~26.9 | Vẫn tính z trên σ nhiễu → z vật ngưỡng cap bằng nhiễu lấy mẫu (2022-Q1/Q2/Q4 đều đổi chỉ vì σ nhỏ) | ⚠️ cần thiết nhưng chưa đủ |
| **C. Robust median/MAD hoặc percentile/rank** | dùng khoảng vị thay z | Tránh được rail | Với 4–6 quý lịch sử, median/MAD/rank **cực kỳ nhiễu** (MAD thường ≈ 0 hoặc vài điểm ngẫu nhiên); percentile cần chục quý mới ổn; khó giải thích trên web/khách hàng | ❌ cho cỡ mẫu hiện tại (có thể xem xét lại khi có ≥ 40 quý) |
| **D. Hybrid giới hạn khoảng cách tới raw** | raw là chính, calibrated chỉ lệch ±25 | 26.25 | Không tự xử lý được z nổ do σ nhiễu (z vẫn ≤ −3) | ⚠️ guardrail tốt nhưng không đủ một mình |
| **E = B + σ-floor + D (CHỌN)** | z tính trên **σ_eff = max(σ_obs, 5.0)**, kẹp \|z\| ≤ 3, sau đó **giữ trong dải [raw−25, raw+25]** rồi mới clip 0–100 | **26.25 (SELL, không còn chạm sàn)** | Thêm 2 tham số — đã nhà balance bằng harness (min_std ∈ {3,5,7}, max_dist ∈ {15,20,25,30}) | ✅ |

### Guardrail E giải quyết từng khuyếm khuyết theo đúng thứ tự nhân quả:

```
σ_eff  = max(σ_obs, min_std=5.0)          # (1) σ nhiễu không còn phóng đại tín hiệu
z      = (raw − μ) / σ_eff , kẹp vào ±3   # (2) bằng chứng có giới hạn — không còn z=±10
cal    = clip(50 + 15·z, raw−25, raw+25)  # (3) calibrated không bao giờ trôi xa raw quá ±25
         rồi clip [0, 100]                # an toàn biên
```

**Lí do min_std = 5.0:** σ quan sát ổn định của chuỗi raw ở trạng thái bình thường là ≈ 6 điểm; mức sàn 5.0 chặn đúng vùng σ "nhiễu mẫu nhỏ" (2–4) mà không đè lên các giai đoạn raw thực sự biến động (σ_obs > 5 vẫn dùng σ_obs). Chỉ 3/24 quý bị floor — đúng 3 quý từng bị bệnh; các quý còn lại **không đổi một số nào** (blast radius tối thiểu, xác minh bằng test sequential rebuild).

**Hệ quả thiết kế có chủ đích:** với z_cap = ±3 và z_scale = 15, lớp z đóng góp tối đa ±45 → calibrated nằm trong [5, 95] ∪ dải quanh raw. **0/100 trở thành không-thể-với-tới bằng cấu trúc** — kịch bản "bằng chứng mạnh và ổn định cho tín hiệu cực đoan" được hiểu thực tiễn là vùng bão hoà 5/95, còn raw composite vẫn tự do chạm 0/100 nếu các factor thật sự sụp đổ (raw không bị winsorise).

## 4. Bảng BEFORE → AFTER (24/24 quý, raw KHÔNG đổi ở bất kỳ quý nào)

Chỉ **3 quý đổi** (in đậm ở cột cuối): 2022-Q1, 2022-Q2, 2022-Q4 — đúng 3 quý có σ_obs < 5.

| Quarter | Raw | ❌ v1 Cal | v1 Label | ✅ v2 Cal | v2 Label | z | σ_eff | floor |
|---|---|---|---|---|---|---|---|---|
| 2021-Q1 | 66.86 | 66.86 | ACCUMULATE | 66.86 | ACCUMULATE | — | — | |
| 2021-Q2 | 62.75 | 62.75 | HOLD | 62.75 | HOLD | — | — | |
| 2021-Q3 | 63.44 | 63.44 | HOLD | 63.44 | HOLD | — | — | |
| 2021-Q4 | 60.22 | 60.22 | HOLD | 60.22 | HOLD | — | — | |
| 2022-Q1 | 59.69 | 30.12 | SELL | **39.12** | **REDUCE** | −0.73 | 5.00 | FLOOR |
| 2022-Q2 | 51.25 | **0.00** | SELL | **26.25** | SELL | −2.27 | 5.00 | FLOOR |
| 2022-Q3 | 57.52 | 40.99 | REDUCE | 40.99 | REDUCE | −0.60 | 5.30 | |
| 2022-Q4 | 45.88 | **6.74** | SELL | **20.88** | SELL | −2.87 | 5.00 | FLOOR |
| 2023-Q1 | 58.49 | 50.08 | HOLD | 50.08 | HOLD | +0.01 | 6.86 | |
| 2023-Q2 | 57.35 | 47.42 | REDUCE | 47.42 | REDUCE | −0.17 | 6.42 | |
| 2023-Q3 | 56.64 | 45.78 | REDUCE | 45.78 | REDUCE | −0.28 | 6.06 | |
| 2023-Q4 | 50.28 | 29.45 | SELL | 29.45 | SELL | −1.37 | 5.77 | |
| 2024-Q1 | 47.02 | 23.54 | SELL | 23.54 | SELL | −1.76 | 5.96 | |
| 2024-Q2 | 53.70 | 42.92 | REDUCE | 42.92 | REDUCE | −0.47 | 6.41 | |
| 2024-Q3 | 49.74 | 33.65 | SELL | 33.65 | SELL | −1.09 | 6.21 | |
| 2024-Q4 | 53.13 | 42.96 | REDUCE | 42.96 | REDUCE | −0.47 | 6.23 | |
| 2025-Q1 | 49.61 | 34.51 | SELL | 34.51 | SELL | −1.03 | 6.07 | |
| 2025-Q2 | 51.03 | 38.94 | REDUCE | 38.94 | REDUCE | −0.74 | 6.07 | |
| 2025-Q3 | 55.20 | 49.86 | REDUCE | 49.86 | REDUCE | −0.01 | 5.98 | |
| 2025-Q4 | 51.98 | 41.55 | REDUCE | 41.55 | REDUCE | −0.56 | 5.81 | |
| 2026-Q1 | 51.47 | 40.48 | REDUCE | 40.48 | REDUCE | −0.63 | 5.70 | |
| 2026-Q2 | 44.38 | 21.85 | SELL | 21.85 | SELL | −1.88 | 5.61 | |
| 2026-Q3 | 46.59 | 30.12 | SELL | 30.12 | SELL | −1.33 | 5.92 | |
| 2026-Q4 | 47.67 | 33.97 | SELL | 33.97 | SELL | −1.07 | 6.01 | |

Kiểm chứng tính chất: monotone trong raw với mọi history cố định ✓; cửa sổ chỉ gồm quý trước (no look-ahead) ✓; |cal − raw| ≤ 25 ✓; không quý nào ở rail 0/100 ✓.

## 5. Kiểm chứng out-of-sample (strict forward return) — công khai cả mặt chưa tốt

Đánh giá signal tại quý t (chỉ dùng dữ liệu tới cuối t−1) với **strict within-quarter forward return** (close t−1 → outcome close t), n = 23:

| Metric | Raw | Calibrated v2 |
|---|---|---|
| Spearman IC | 0.193 | **0.342** |
| Sign hit-rate | 47.8% | 56.5% |

Đối chiếu **forward return liên tiếp t→t+1** (n = 22): IC raw ≈ **−0.03**, calibrated ≈ **0.18**, hit ≈ 50%.

**Kết luận trung thực:** sức mạnh định hướng ở mức vừa phải; calibration v2 cải thiện IC so với raw trên cả 2 cách đo — nhưng đây KHÔNG phải alpha mạnh và không được marketing như "dự báo lợi nhuận quý". Tier 2 là tín hiệu **phân bổ/regime tương đối**, cần kết hợp với định giá và bối cảnh; giá trị chính là khôi phục dispersion để sizing (trước đây 16/24 quý HOLD khiến phân bổ vô dụng) đồng thởi không biến tín hiệu trung tính thành cực đoan.

Backtest chiến lược dashboard-compatible (formula-verified trong workbook, audit 8,905 checks PASS): CAGR 5.74%, MDD −9.02%, Vol 7.70%, Sharpe (rf 4.5%) 0.16, IC(raw) 0.193.

## 6. Artifact đã rebuild & đồng nhất (sequential rebuild 2021-Q1 → 2026-Q4)

- `data/scores/quarterly_scores_history.parquet` — 24 hàng, raw & calibrated **lưu 2 tầng riêng** + đầy đủ diagnostics v2 (`calibration_z`, `calibration_z_raw`, `calibration_hist_mean/std`, **`calibration_std_effective`**, **`calibration_std_floored`**, `calibration_n_history`, `calibration_method="winsorized_expanding_z_v2"`, `calibration_applied`).
- 24 × `output/exports/score_20XX_QX.json` — như trên + metadata provenance: `git_commit`, `config_hash`, `model_hash`, `data_as_of`, `generated_at`, **`status` FINAL/PROVISIONAL** (rule tổng quát từ data_as_of, không hardcode), `calibration_method`, `model_version`, `point_in_time`.
- 24 × HTML quý + dashboard root — hero hiển thị calibrated, diagnostics σ-floor hiển thị cho 3 quý bị floor, legend "relative regime — NOT a forecast".
- 2 canonical Excel: `VN_Index_Quant_Model_Complete_Architecture.xlsx` (alias byte-identical `VN_Index_Quant_Scoring_Model_Master.xlsx`) — sheet 05 công thức v2, config rows 38–42 chứa tham số guardrail (single source of truth đọc từ `config.py`), audit `verify_workbook_accuracy.py` PASS (0 formula error, ±0.05 toàn bộ).
- `output/exports/VN_Index_Quant_Scoring_Model.xlsx` (excel_builder, 7 sheets — subtitle v2) + `VN_Index_Detailed_Data_Export.xlsx` (20 sheets).
- `README.md` auto-generated block (qua `scripts/update_readme_results.py`) + disclosure thủ công ở § kiểm chứng.

## 7. Trạng thái xuất bản & provenance tại thởi điểm viết (2026-09-29)

- **2026-Q4: PROVISIONAL** — `data_as_of = 2026-09-25 < 2026-09-30` (close tạm 1780.68 cho return reference). Sẽ tự chuyển FINAL khi pipeline chạy lại với source ≥ 30/09/2026; **không chốt tay giá trị số**.
- Tất cả quý ≤ 2026-Q3: FINAL (as-of/date nguồn đã tới cuối quý ± tolerance cuối tuần).
- Kiến trúc as-of của scoring **không đổi**: decision tại cuối t−1, outcome tối đa cuối t; PIT close 2021-Q1 = 1103.87 (2020-12-31), 2021-Q2 = 1191.44 (2021-03-31) — khớp artifact, không có valuation/backfill giả.

## 8. Thiếu sót còn lại (honest missing-fields list)

1. **Cỡ mẫu lịch sử còn nhỏ** (tối đa 23 quý): percentile/rank robust (option C) chưa áp dụng được — xem xét lại khi ≥ 40 quý.
2. 4 quý 2021-Q1→Q4 vẫn N/A `pe_zscore/pb_zscore/eyg_zscore` (giới hạn dữ liệu thật ex-Vingroup từ 2020-12; đã ghi rõ trong README — **không bịa**).
3. `generated_at` của HTML giữ nguyên dấu tạo lại mới nhất; `status` là quy tắc suy từ `data_as_of` — nếu muốn "FINAL theo quyết định con ngưởi" cần thêm field phê duyệt (chưa có trong scope).
4. Test CI mô phỏng thất bại nguồn (API down) chưa có — workflows đã fail-hard, nhưng chưa có unit test giả lập lỗi nguồn (đề xuất issue tiếp theo).
5. IC/hit-rate đo trên n=22–23 quý — significance thấp; cần thu thập thêm quý để kết luận chắc hơn.

## 9. Làm sao self-check cho quý tương lai (2027-Q1+)

- Thêm quý mới → chạy `scripts/backfill_calibrated_scores.py` (sequential, idempotent, chỉ tính lại calibrated từ raw của parquet) → `scripts/rebuild_html.py` → `scripts/update_readme_results.py` → `generate_english_master_workbook.py` → `verify_workbook_accuracy.py` → `scripts/generate_excel_report.py` → `scripts/export_excel_detailed.py`.
- Chạy `pytest tests/` — các regression test sau sẽ bắt lỗi lặp lại:
  - `test_score_calibration.py` — unit v2: prior-only, small-σ không về 0, winsorise, monotone, guardrail ±25, sequential 24-quý, mở rộng 2027-Q1.
  - `test_calibration_v2_artifacts.py` — artifact contract: raw/calibrated tách bạch, provenance, không rail, idempotent rebuild, status FINAL/PROVISIONAL, web↔JSON, forward-return IC khớp workbook.
  - `test_hma_pre_release_pit.py`, `test_future_quarter_workbook.py` — PIT & không cửa sổ cố định 24 quý.
