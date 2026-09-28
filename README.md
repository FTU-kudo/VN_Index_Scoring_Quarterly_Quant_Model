# 📊 VN-Index Quarterly Quantitative Scoring Model
### Hệ Thống Định Lượng Toàn Diện Đánh Giá & Chấm Điểm Thị Trường Chứng Khoán Việt Nam Đầu Mỗi Quý

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Market](https://img.shields.io/badge/Market-Vietnam%20(HOSE%20%7C%20HNX%20%7C%20UPCOM)-success.svg)]()
[![Framework](https://img.shields.io/badge/Framework-Econometrics%20%2B%20Machine%20Learning-orange.svg)]()
[![Automation](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions%20Scheduled-brightgreen.svg)]()

---

## 🎯 TỔNG QUAN HỆ THỐNG (EXECUTIVE OVERVIEW)

**VN_Index_Scoring_Quarterly_Quant_Model** là hệ thống định lượng tài chính cấp quản lý quỹ đầu tư (Fund Manager / CFA charterholder level), được phát triển nhằm mục tiêu giải quyết bài toán cốt lõi:

> *"Vào ngày giao dịch đầu tiên của mỗi quý tài chính, thị trường chứng khoán Việt Nam (VN-Index) đang ở chu kỳ nào? Mức độ hấp dẫn đầu tư đạt bao nhiêu điểm trên thang 100? Quỹ đầu tư nên phân bổ tỷ trọng tài sản (Asset Allocation) như thế nào để tối ưu hóa Sharpe Ratio và bảo vệ danh mục trước các đợt sụt giảm lớn (Maximum Drawdown)?"*

Hệ thống được thiết kế đáp ứng trọn vẹn **5 Tiêu chuẩn Vàng**:
1. **Xác định toàn diện các biến số**: Tích hợp 4 trụ cột định lượng (Vĩ mô & Tiền tệ, Định giá lịch sử, Dòng tiền & Margin, Động lượng Kỹ thuật).
2. **Định lượng hóa chặt chẽ**: Ứng dụng Hồi quy Đa biến (MLR với Newey-West HAC robust errors), Mô hình Tự hồi quy Vectơ (VAR với Granger Causality & IRF), và Machine Learning (XGBoost / Random Forest).
3. **Thu thập dữ liệu tự động & thực tế**: Tích hợp trực tiếp với API `vnstock` thế hệ mới (`Quote`, `Listing`) và API VNDirect.
4. **Tự động hóa 100%**: Sẵn sàng với CI/CD GitHub Actions chạy tự động vào đầu mỗi quý và tự động Deploy Báo cáo HTML lên GitHub Pages.
5. **Kiểm định thực nghiệm nghiêm ngặt (Backtest & WFV)**: Áp dụng phương pháp Walk-Forward Validation (WFV) trượt tránh rò rỉ thông tin tương lai (Data Leakage). Mô hình đã được backtest thành công trên **24 quý liên tiếp (Q1/2021 đến Q4/2026)**.

---

## 📐 SÁU TRỤ CỘT ĐỊNH LƯỢNG (6 PILLARS & COMPOSITE SCORING)

Hệ thống đánh giá thị trường dựa trên thang điểm chuẩn hóa **100 điểm**, phân bổ trọng số theo 6 nhóm biến số. Đây là bộ trọng số **duy nhất** (Single Source of Truth), được định nghĩa tại [`src/utils/config.py`](src/utils/config.py):

| # | Trụ cột | Trọng số | Các chỉ báo chính | Ghi chú |
|---|---------|:--------:|---------------------|---------|
| 1 | **Macro & Monetary** | **25%** | VN1Y Yield, ΔIR, USD/VND Z-score, M2 YoY, VN10Y Yield, Yield Spread | Môi trường lãi suất & tiền tệ |
| 2 | **Global & Intermarket** | **20%** | DXY Z-score, US10Y Yield, USD/JPY Z-score, Net Foreign Flow Z-score | Áp lực toàn cầu & dòng vốn ngoại |
| 3 | **Valuation & Leverage** | **20%** | P/E Z-score 5Y, P/B Z-score 5Y, Margin Risk, Earnings Yield Gap | Định giá tương đối & rủi ro đòn bẩy |
| 4 | **Quant Model (MLR + VAR)** | **15%** | MLR predicted return, VAR T+5 forecast, Adj-R², Granger leaders | Tín hiệu từ mô hình kinh tế lượng |
| 5 | **ML Forecast** | **10%** | XGBoost WFV accuracy, F1-score, directional prediction | Tín hiệu Machine Learning |
| 6 | **Market Structure & FTSE** | **10%** | FTSE upgrade status, rebalancing proximity, ADTV change | Cấu trúc vi mô & nâng hạng |

> **⚠️ Lưu ý về phương pháp luận (Methodology Notes):**
> - **Point-in-time đầu quý (nguyên tắc buy-side)**: Quyết định phân bổ được ra vào ngày giao dịch đầu tiên của quý, do đó điểm số quý Q chỉ được tính từ dữ liệu có đến hết phiên cuối cùng của quý Q-1 — áp dụng **đồng nhất cho cả chạy live lẫn backfill lịch sử** (xem `src/utils/dates.py`). Các cột `*_q_ytd` tại cut-off này chính là giá trị cộng dồn trọn quý vừa kết thúc. Trường `data_as_of` trong mỗi JSON export cho phép audit chính xác điểm được tính từ thông tin đến ngày nào. Lần chạy giám sát giữa quý dùng `--as-of YYYY-MM-DD` và bị đánh dấu `point_in_time=false` để không lẫn vào backtest.
> - **Hệ số quy đổi (chống nén tín hiệu)**: Các hàm chuyển đổi raw → score 0-100 (ví dụ: `vn1y_score = 100 - (vn1y-1.0)*14.0`) là heuristics được calibrate theo expert judgment. Tín hiệu mô hình dùng gain mạnh để không bị bóp chết: `mlr_score = 50 + pred*20000` (±0.10%/ngày → 70/30), `var_score = 50 + pred*5000`. Tín hiệu MISSING (MLR/VAR/ADTV/ETF) **không tham gia trung bình trụ cột** — trung bình được renormalize theo số tín hiệu có thật, thay vì fallback trung lập 50 kéo mọi thứ về giữa.
> - **Chỉ báo kỹ thuật ngắn hạn**: Một số indicators (RSI-14, MACD daily) có chu kỳ ngắn hơn đáng kể so với tần suất ra quyết định hàng quý (3 tháng). Hệ thống sử dụng giá trị snapshot tại thời điểm chấm điểm — đây là trade-off có chủ đích giữa tính kịp thời (timeliness) và tính ổn định (stability).
> - **Most Divergent Pillar**: Trường `most_divergent_pillar` trong output là nhóm có raw score lệch xa 50 nhất — đây là heuristic đơn giản, KHÔNG phải kết quả từ Granger Causality test. Granger tests được dùng riêng trong mô hình VAR để xếp hạng biến giải thích.

---

## 🎚️ HAI TẦNG ĐIỂM: RAW COMPOSITE + CALIBRATED ACTION SIGNAL

Hệ thống dùng kiến trúc **2 tầng điểm** để khắc phục hiện tượng "HOLD mãn tính" (22/24 quý bị nhãn HOLD do điểm thô bị nén trong dải hẹp 45.8–61.4 — vô dụng cho phân bổ tài sản):

| Tầng | Tên | Công thức | Vai trò |
|:---:|---|---|---|
| **1** | **Raw Composite** (`total_score`) | 6 trụ cột × trọng số, thang 0–100 | Tầng **tham chiếu** — giữ nguyên qua mọi kỳ, dùng so sánh lịch sử & backtest |
| **2** | **Calibrated Action Signal** (`calibrated_score`) | `clip(50 + 15 × z, 0, 100)` với `z = (total − μ_hist)/σ_hist` trên **cửa sổ expanding CHỈ gồm các quý TRƯỚC** (point-in-time, không look-ahead) | Tầng **hành động** — nhãn phân bổ tài sản (BUY/ACCUMULATE/HOLD/REDUCE/SELL) |

**Thông số** nằm trong `config.py → SCORE_CALIBRATION` (single source of truth): `center=50`, `z_scale=15`, `min_history=4`, clip `[0, 100]`. Quý đầu tiên (< 4 quý lịch sử) hoặc σ_hist ≈ 0 → **giữ nguyên điểm thô**, `calibration_applied=false`. Nhãn lấy từ `get_score_label()` — cùng bộ ngưỡng với tầng raw.

**Kết quả backfill 24 quý (2021-Q1 → 2026-Q4)** — *sau backfill dữ liệu thật 09/2026 (ADTV, trái phiếu full-history, M2 ADB/GSO, P/E-P/B-EYG Z-score):*

| Phân bố nhãn | Trước (raw) | Sau (calibrated) |
|---|:---:|:---:|
| 🟢 BUY | 0 | 0 |
| 🔵 ACCUMULATE | **1** | **1** |
| 🟡 HOLD | **19** | **6** |
| 🟠 REDUCE | **4** | **9** |
| 🔴 SELL | 0 | **8** |

Các quý gấu 2022 và giai đoạn 2026 ra tín hiệu phòng thủ đúng: **2022-Q2 = SELL (11.8)**, 2022-Q3 = REDUCE (43.6), **2022-Q4 = SELL (22.1)**, **2026-Q2 = SELL (17.0)**, quý live **2026-Q4 = SELL (28.2)**; chu kỳ nới lỏng đầy đủ 2020 nâng quyết định đầu tiên **2021-Q1 = ACCUMULATE (70.1)** (VN1Y 0.43%, M2 +14.5% — trước đây cả hai đều N/A default 50).

> **📈 Nguồn dữ liệu ADTV (từ 09/2026 — hết N/A 24/24 quý):** `ADTV change = ADTV(Q−1)/ADTV(Q−2) − 1` tính point-in-time từ cột `volume` của OHLCV VN-Index (vnstock, nguồn VCI) — quyết định quý Q chỉ dùng 2 quý **đã kết thúc** trước đó. Điểm ADTV = `clip(50 + 100 × %thay đổi, 0, 100)`. Ví dụ: 2025-Q4 bùng nổ thanh khoản +65.7% QoQ → score 100; 2026-Q1 điều chỉnh −38.4% → score 12. Audit đầy đủ: `data/scores/vnindex_quarterly_adtv.json`.

> **📥 Nguồn dữ liệu backfill 09/2026 — trái phiếu + M2 + Z-score (nguồn thật, không suy đoán):**
> - **Trái phiếu (24/24 quý có dữ liệu)**: đường cong fitted Nelson-Siegel từ repo `VN_Bond_Yield_pipeline` — chuyển sang bản **full-history** `fitted_curve_ns_full.json` (2012-08-06 → nay, 3.397 ngày) thay cho bản cắt dashboard chỉ từ 2022-09-22. VN1Y/ΔVN1Y/VN10Y/spread 10Y−2Y lấy as-of point-in-time; **pre-check: 68/68 giá trị tính lại khớp tuyệt đối** với các quý vốn có dữ liệu. Fixes 7 quý 2021-Q1→2022-Q3 từng N/A (VN1Y 0.43–1.82%, VN10Y 1.91–3.20%).
> - **M2 (24/24 quý có dữ liệu)**: ADB Key Indicators Database (SDMX `FM2_PTX_PS.VIE`, nguồn gốc số liệu SBV) 2000→2024 + GSO Báo cáo KT-XH quý IV/2025 (tổng PTTT **+14,98%** đến 22/12/2025). Point-in-time bằng `merge_asof` backward — quyết định quý Q nhận giá trị năm gần nhất **đã công bố** (2021-Q* ← 2020 = +14.53%, 2022-Q* ← 2021 = +10.66%, 2023-Q1/Q2 ← 2022 = +6.15% …). 2026 chưa có số công bố → dùng 2025. Fallback committed: `data/external/m2_credit_adb_gso.csv` (kèm README nguồn từng số).
> - **P/E-P/B-EYG Z-score**: min_periods hạ từ 2,5 năm (630 phiên) xuống **252 phiên** (~1 năm) vì series P/E ex-Vingroup chỉ bắt đầu ~2020-12 (thiếu số cổ phiếu lưu thông trước đó). z đầu tiên hợp lệ 2021-12-20 → fixes pe_zscore 6 quý 2022-Q1→2023-Q2; **giá trị Z các ngày đủ 2,5 năm dữ liệu giữ nguyên** (pre-check 28/28 khớp). EYG = 1/PE − VN10Y giờ được truyền đúng qua `df_macro` — trước đây **âm thầm default 50 ở cả 24/24 quý**.
> - Audit input thật từng quý: `data/scores/vnindex_quarterly_market_data.json`.

> **🚧 N/A còn lại sau backfill 09/2026 — giới hạn dữ liệu THẬT, cố tình không điền:**
> - `nff_ex_etf` / `etf_flow` z-score: **5 quý 2021-Q1→2022-Q1**. API VNDirect (nguồn giao dịch khối ngoại) chỉ phục vụ dữ liệu từ 2021-01; z-score cần 4 quý đã kết thúc trước đó → quý sớm nhất có z là 2022-Q2. Không có nguồn giao dịch khối ngoại HOSE 2019-2020 tiếp cận được theo chương trình.
> - `pe_zscore` / `pb_zscore` / `eyg_zscore`: **4 quý 2021-Q1→Q4**. Series P/E-P/B ex-Vingroup (tính từ market cap = giá × số cổ phiếu lưu thông) chỉ bắt đầu ~2020-12 trong bộ dữ liệu PE_PB_HOSE_stocks; cần 252 phiên cho z-score → z đầu tiên 2021-12-20, sau as-of của mọi quyết định 2021 (mới nhất là 2021-09-30) nên 2021-Q1→Q4 vẫn N/A; quyết định 2022-Q1 (as-of 2021-12-31) trở đi đã có z thật.
> - Nguyên tắc: **thiếu dữ liệu → default trung lập 50 (hoặc renormalize), không nội suy, không suy đoán**. Mọi con số trong exports đều truy vết được về nguồn công bố.

> **⚠️ Báo cáo trung thực về chất lượng tín hiệu:** Tầng calibrated **không** làm tăng sức mạnh dự báo phương hướng — IC (Spearman) của calibrated score so với forward return quý sau ≈ 0.02 (raw ≈ 0.09), hit-rate ~50%. Giá trị của tầng 2 là **khôi phục độ phân tán regime** để khung phân bổ tài sản có tín hiệu khác biệt giữa các kỳ (trước đây 22/24 quý "HOLD" khiến sizing bất khả thi), chứ không phải alpha prediction. Chi tiết backtest trung thực: sheet `06_Signal_Efficacy` trong Excel workbook.

---

## 🔬 MÔ HÌNH KINH TẾ LƯỢNG & MACHINE LEARNING

Hệ thống kết hợp ba tầng mô hình phân tích định lượng:

### 1. Mô hình Hồi quy Đa biến (Multi-Linear Regression - MLR)
Thiết lập phương trình dự báo lợi suất VN-Index chu kỳ tiếp theo $R_{t+h}$:

$$
R_{t+h} = \alpha + \beta_1 \Delta \text{VN1Y}_t + \beta_2 \Delta \text{US10Y}_t + \beta_3 \Delta \text{DXY}_t + \beta_4 \text{NFF}_t + \beta_5 \text{PE-Zscore}_t + \beta_6 \Delta \text{Margin}_t + \beta_7 \Delta \text{USD/JPY}_t + \epsilon_t
$$
- **Dự báo thuần túy (Predictive, không nowcast)**: Biến phụ thuộc là **trung bình log-return/ngày của $h = 21$ phiên kế tiếp** ($t+1 \dots t+h$, ~1 tháng giao dịch); biến giải thích chỉ dùng thông tin đã biết tại cuối phiên $t$ — không chứa return cùng ngày.
- **Newey-West HAC Standard Errors**: Tự động hiệu chỉnh sai số nhằm giải quyết hiện tượng phương sai thay đổi (Heteroskedasticity) và tự tương quan (Autocorrelation); `maxlags ≥ h` để xử lý autocorrelation phát sinh từ overlapping forward windows.
- **Đánh giá Out-of-Sample**: Model được đánh giá trên 25% dữ liệu cuối (holdout, không shuffle) với hit-rate (đúng dấu) và OOS R² — thước đo trung thực về khả năng dự báo, tách biệt với R² in-sample.
- **Phân tích độ nhạy**: Đánh giá chính xác $p$-value và hệ số $\beta$ chuẩn hóa để xếp hạng mức độ ảnh hưởng của từng biến số.

### 2. Mô hình Tự Hồi quy Vectơ (Vector Autoregression - VAR)
- **Lag selection**: Tự động lựa chọn độ trễ tối ưu dựa trên tiêu chuẩn thông tin Akaike (AIC) và Schwarz-Bayesian (BIC).
- **Granger Causality Test**: Kiểm tra kiểm định nhân quả theo thời gian để xác định xem sự thay đổi của biến số vĩ mô (ví dụ: DXY, Lợi suất VN1Y, Tỷ giá USD/JPY) dẫn dắt VN-Index trước bao nhiêu tuần.
- **Impulse Response Functions (IRF)**: Mô phỏng cú sốc (1 độ lệch chuẩn) từ US10Y, DXY, hoặc USD/JPY (hiệu ứng Yen Carry Trade unwind) tác động lên quỹ đạo VN-Index trong 12 kỳ tiếp theo.

### 3. Mô hình Học máy & Kiểm định Trượt (XGBoost + Walk-Forward Validation)
- **Cấu trúc bộ phân loại**: Phân loại xu hướng 3 trạng thái thị trường: `UP` (+1), `SIDEWAY` (0), `DOWN` (-1).
- **Walk-Forward Validation (WFV)**:
  - Khung thời gian huấn luyện trượt (Rolling Training Window = 250 - 500 phiên).
  - Kiểm tra hoàn toàn Out-Of-Sample (OOS) trên các chu kỳ tiếp theo, loại bỏ 100% rủi ro Look-ahead bias.
  - Trích xuất Feature Importance để đối chiếu với hệ số hồi quy của mô hình kinh tế lượng.

---

## 🎖️ THANG ĐIỂM & MA TRẬN PHÂN BỔ TÀI SẢN (ASSET ALLOCATION MATRIX)

Bộ ngưỡng **duy nhất** từ `config.py → SCORE_LABELS` (test `test_score_label_sync` tự động FAIL nếu có nơi nào hardcode lại ngưỡng). Áp dụng cho **cả 2 tầng** — nhãn hành động thực tế lấy từ tầng calibrated:

| Khoảng Điểm | Xếp Hạng Khuyến Nghị | Màu trên Dashboard/Excel | Tỷ Trọng Cổ Phiếu (% NAV) | Tỷ Trọng Tiền Mặt / Trái Phiếu | Chiến Lược Quản Trị Rủi Ro |
|:---:|:---:|:---:|:---:|:---:|---|
| **80 – 100** | 🟢 **MUA (BUY)** | 🟢 Xanh lá `#10b981` | 85% – 100% | 0% – 15% | • Full vị thế cổ phiếu dẫn dắt (VN30)<br>• Cân nhắc sử dụng Margin chọn lọc |
| **65 – 79** | 🔵 **TÍCH LŨY (ACCUMULATE)** | 🔵 Xanh dương `#3b82f6` | 70% – 85% | 15% – 30% | • Tích lũy cổ phiếu cơ bản tốt khi có điều chỉnh<br>• Duy trì đòn bẩy an toàn |
| **50 – 64** | 🟡 **NẮM GIỮ (HOLD)** | 🟡 Vàng `#eab308` | 40% – 60% | 40% – 60% | • Cân bằng danh mục, tập trung cổ phiếu trả cổ tức cao<br>• Tuyệt đối không dùng margin cao |
| **35 – 49** | 🟠 **GIẢM TỶ TRỌNG (REDUCE)** | 🟠 Cam `#f97316` | 20% – 40% | 60% – 80% | • Hạ tỷ trọng cổ phiếu beta cao<br>• Đưa margin về 0, chốt lời từng phần |
| **0 – 34** | 🔴 **BÁN (SELL)** | 🔴 Đỏ `#ef4444` | 0% – 20% | 80% – 100% | • Giữ tối đa tiền mặt / chứng chỉ tiền gửi<br>• Mở vị thế short phái sinh VN30F để hedge |

Trên **dashboard 24 quý**, thẻ & timeline tô màu theo **regime calibrated** (4–5 màu); đường **raw composite** giữ **nét đứt** làm tham chiếu. Trong **báo cáo quý**, hero hiển thị điểm thô + chip nổi bật `⚡ HÀNH ĐỘNG: {calibrated_label} — {calibrated_score}` và Action Panel chạy theo calibrated (marker, allocation, dòng z-diagnostic: `z, μ_hist, σ_hist, n`).

---

<!-- AUTO_RESULTS_START -->
## 📊 KẾT QUẢ THỰC NGHIỆM MẪU (AUTO-GENERATED)

> **⚠️ Section này được tạo TỰ ĐỘNG bởi `scripts/update_readme_results.py` từ dữ liệu output thực tế.**
> **Không chỉnh sửa thủ công — sẽ bị ghi đè khi chạy pipeline.**

```text
======================================================================
     VN-INDEX QUANTITATIVE SCORING — 2026-Q4
     Generated: 2026-09-27T21:52:19.513880
======================================================================
[MARKET DATA]
  • VN-Index Close         : N/A
  • US 10Y Yield           : N/A%
  • DXY Index              : N/A
  • RSI (14D)              : N/A

[ECONOMETRICS: MLR MODEL]
  • N observations         : N/A
  • R-squared              : N/A (R-adj = N/A)

[MACHINE LEARNING: WALK-FORWARD VALIDATION]
  • XGBoost Accuracy       : 0.4250
  • N Folds (WFV)          : 8
  • Latest Prediction      : DOWN

[COMPOSITE SCORE & ALLOCATION]
  • Total Score (raw)      : 47.32 / 100
  • Classification (raw)   : 🟠 REDUCE — Reduce exposure — Increasing pressure
  • Calibrated Action      : 🔴 SELL — 28.24 / 100 (0–20% Equities)
  • Calibration z          : -1.45

[GROUP BREAKDOWN]
  • macro_monetary                : raw=  57.9  weight=14.48
  • global_intermarket            : raw=  37.2  weight=7.44
  • valuation_leverage            : raw=  42.9  weight=8.57
  • quant_model                   : raw=  54.9  weight=8.24
  • ml_forecast                   : raw=  25.9  weight=2.59
  • market_structure              : raw=  60.0  weight=6.0
======================================================================
```
<!-- AUTO_RESULTS_END -->

---

## 📁 CẤU TRÚC DỰ ÁN (PROJECT REPOSITORY LAYOUT)

```text
VN_Index_Scoring_Quarterly_Quant_Model/
├── .github/
│   └── workflows/
│       ├── quarterly_scoring.yml   # CI/CD: Chạy tự động đầu mỗi quý (01/01, 01/04, 01/07, 01/10)
│       ├── batch_scoring.yml       # CI/CD: Chạy backtest quét toàn bộ 24 quý lịch sử
│       └── validate_data.yml       # CI/CD: Kiểm định dữ liệu hàng ngày (Thứ 2 - Thứ 6)
├── data/
│   ├── raw/                       # Chứa cache dữ liệu thô (vn30_tickers.json, macro_sbv.csv)
│   ├── processed/                 # Dữ liệu sạch đã căn chỉnh mốc thời gian
│   └── features/                  # Ma trận đặc trưng 4 nhóm biến số
├── output/
│   ├── exports/                   # Tệp JSON xuất kết quả điểm số (score_*.json) + Excel Quant Factor Workbook
│   ├── reports/                   # Báo cáo phân tích HTML / Markdown hoàn chỉnh (index.html = dashboard 24 quý)
│   └── charts/                    # Biểu đồ phân rã điểm số và hàm phản ứng xung
├── scripts/
│   ├── backfill_calibrated_scores.py  # Backfill idempotent cột calibrated cho 24 quý (parquet + JSON)
│   ├── rebuild_html.py            # Rebuild 24 báo cáo HTML + dashboard + validate + Excel
│   ├── generate_excel_report.py   # Xuất Excel Quant Factor Workbook 8 sheet
│   ├── inject_vnindex_chart.py    # Validator: VN-Index overlay (fail loudly nếu thiếu)
│   └── inject_navbar.py           # Validator: navbar quarter navigation (fail loudly nếu thiếu)
├── src/
│   ├── data/
│   │   └── fetcher.py             # Data Ingestion: vnstock 4.0.2 (Quote, Listing) & yfinance
│   ├── features/
│   │   ├── macro_features.py      # Trụ cột 1: Lãi suất, DXY, US10Y, Tỷ giá, M2
│   │   ├── valuation_features.py  # Trụ cột 2: P/E, P/B Z-scores, ERP
│   │   ├── flow_features.py       # Trụ cột 3: Net Foreign Flow VN30, Margin debt
│   │   ├── technical_features.py  # Trụ cột 4: RSI, MACD, BB, Volatility (Pure NumPy/Pandas)
│   │   └── global_features.py     # Tương quan liên thị trường toàn cầu
│   ├── models/
│   │   ├── regression/
│   │   │   └── mlr_model.py       # Multi-Linear Regression với Newey-West HAC
│   │   ├── var/
│   │   │   └── var_model.py       # Vector Autoregression + Granger Causality + IRF
│   │   └── ml/
│   │       └── ml_model.py        # XGBoost / Random Forest + Walk-Forward Validation
│   ├── scoring/
│   │   ├── quarterly_scorer.py    # Bộ tính điểm 2 tầng: raw composite + calibrate_total_score() (Calibrated Action Signal)
│   │   └── backtester.py          # Kiểm định chiến lược phân bổ tài sản lịch sử
│   ├── reporting/
│   │   ├── report_builder.py      # Báo cáo HTML 2 tầng + dashboard + VN-Index overlay (tích hợp, không inject)
│   │   └── excel_builder.py       # Excel Quant Factor Workbook 8 sheet (KPI CALIBRATED ACTION)
│   └── utils/
│       └── config.py              # Cấu hình trung tâm: SCORE_LABELS + SCORE_CALIBRATION + get_vn30_tickers() động
├── tests/
│   ├── conftest.py                # Test hygiene: cách ly SCORES_DIR (pytest không chạm data/ production)
│   ├── test_score_calibration.py  # 13 tests: công thức calibrated, clip, fallback, point-in-time, SSOT, gains
│   └── ...                        # MLR forecast, point-in-time dates, label sync, scoring weights
├── .env.example                   # Mẫu cấu hình API key (VNSTOCK_API_KEY, Telegram, SMTP)
├── .gitignore                     # Đã cấu hình loại trừ file nhạy cảm và handoff notes
├── LICENSE                        # Giấy phép mã nguồn mở GNU AGPL v3.0
├── requirements.txt               # Danh sách gói phụ thuộc tương thích Python 3.11 - 3.14
├── run_quarterly.py               # Entrypoint chính thức chạy pipeline theo quý
└── run_daily_update.py            # Entrypoint cập nhật tín hiệu hàng ngày sau giờ đóng cửa
```

---

## 🚀 HƯỚNG DẪN CÀI ĐẶT & SỬ DỤNG (QUICKSTART)

### 1. Yêu cầu Môi trường
- **Python**: `>= 3.11` (Hỗ trợ và kiểm định tương thích hoàn hảo trên **Python 3.14**).
- **Hệ điều hành**: Windows / macOS / Linux.

### 2. Cài đặt Môi trường
```bash
# Clone repository
git clone https://github.com/FTU-kudo/VN_Index_Scoring_Quarterly_Quant_Model.git
cd VN_Index_Scoring_Quarterly_Quant_Model

# Khởi tạo và kích hoạt môi trường ảo
python -m venv .venv

# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# Cài đặt các thư viện cần thiết
pip install -r requirements.txt
```

### 3. Cấu hình Khóa API (`.env`)
Tạo file `.env` từ file mẫu:
```bash
cp .env.example .env     # Linux / macOS
copy .env.example .env   # Windows
```
Chỉnh sửa file `.env` và thêm khóa API vnstock của bạn:
```ini
VNSTOCK_API_KEY=your_vnstock_api_key
```

---

### 4. Vận hành Mô hình

#### Cách 1: Chạy Full Pipeline Theo Quý (`run_quarterly.py`)
```bash
# Chạy chấm điểm cho quý hiện tại:
python run_quarterly.py --quarter 2026-Q3

# Các tùy chọn nâng cao:
python run_quarterly.py --quarter 2026-Q3 --no-cache      # Buộc tải lại toàn bộ dữ liệu mới nhất
python run_quarterly.py --quarter 2026-Q3 --skip-ml       # Bỏ qua bước huấn luyện ML để kiểm tra nhanh
```
Pipeline tự động tính **cả 2 tầng điểm** (raw composite + calibrated action signal), ghi cột `calibrated_score`/`calibrated_label` vào `data/scores/quarterly_scores_history.parquet`, rồi auto-sync README + toàn bộ báo cáo HTML + Excel.

#### Cách 2: Backfill Calibrated Action Signal cho lịch sử (`scripts/backfill_calibrated_scores.py`)
Idempotent — chỉ **THÊM** cột/field calibrated vào 24 quý lịch sử (parquet + toàn bộ `output/exports/score_*.json`), **KHÔNG sửa** điểm thô; tự lọc bỏ row test `2099-Q1` nếu lọt vào parquet:
```bash
python scripts/backfill_calibrated_scores.py
# In ra bảng so sánh raw vs calibrated + phân bố nhãn cho từng quý
```

#### Cách 3: Rebuild Toàn bộ Báo cáo HTML + Dashboard + Excel (`scripts/rebuild_html.py`)
```bash
python scripts/rebuild_html.py
# 24 báo cáo quý + dashboard root + validate VN-Index overlay & navbar
# (exit code != 0 nếu thiếu feature — chống gãy âm thầm) + Excel workbook
```

#### Cách 4: Xuất Excel Quant Factor Workbook (`scripts/generate_excel_report.py`)
```bash
python scripts/generate_excel_report.py
# -> output/exports/VN_Index_Quant_Factor_Analysis.xlsx (8 sheet)
#    00_Dashboard: KPI "CALIBRATED ACTION" | 01_Score_History: cột calibrated
#    06_Signal_Efficacy: backtest theo tín hiệu calibrated (raw để đối chiếu)
```

#### Cách 5: Chạy Cập nhật Tín hiệu Hàng ngày (`run_daily_update.py`)
Dùng sau 16:05 ICT mỗi ngày giao dịch để kiểm tra diễn biến giá, dòng tiền khối ngoại và cảnh báo biến động bất thường:
```bash
python run_daily_update.py
```

---

## 🤖 TỰ ĐỘNG HÓA CI/CD (GITHUB ACTIONS)

Dự án tích hợp sẵn 4 workflows tự động trong `.github/workflows/`:
1. **`quarterly_scoring.yml`**:
   - Tự động kích hoạt vào lúc 09:00 ICT ngày đầu tiên của mỗi quý (ngày 1 các tháng 1, 4, 7, 10).
   - Tự động fetch dữ liệu, tính điểm composite, xuất báo cáo HTML và lưu trữ Artifacts trên GitHub.
   - Hỗ trợ kích hoạt thủ công qua nút **Run workflow** trên giao diện GitHub Actions (`workflow_dispatch`).
2. **`batch_scoring.yml`**:
   - Tự động chạy quét backtest toàn bộ 24 quý lịch sử khi cần tính toán lại dữ liệu quy mô lớn, báo cáo tổng hợp các trường hợp fail.
3. **`deploy_pages.yml`**:
   - Tự động publish toàn bộ thư mục `output/reports` lên Internet thông qua **GitHub Pages** mỗi khi có commit mới vào nhánh main, giúp nhà quản lý quỹ xem báo cáo mọi lúc mọi nơi.
4. **`validate_data.yml`**:
   - Tự động kiểm tra chất lượng kết nối API và tính toàn vẹn dữ liệu từ Thứ 2 đến Thứ 6 hàng tuần.

---

## ⚖️ GIẤY PHÉP (LICENSE)

Dự án được phân phối dưới giấy phép **GNU Affero General Public License v3.0 (AGPL-3.0)**. Xem chi tiết tại tệp [LICENSE](LICENSE).

---

## ⚠️ TUYÊN BỐ MIỄN TRỪ TRÁCH NHIỆM (DISCLAIMER)

> Hệ thống phân tích định lượng này được xây dựng cho mục đích **nghiên cứu học thuật, phân tích kinh tế lượng và kiểm nghiệm mô hình đầu tư**.
> Mọi số liệu, xếp hạng điểm số và ma trận phân bổ tài sản do mô hình xuất ra không cấu thành lời mời chào hay khuyến nghị mua/bán bất kỳ chứng khoán cụ thể nào. Nhà đầu tư chịu trách nhiệm hoàn toàn đối với các quyết định đầu tư và quản trị rủi ro vốn của chính mình.
