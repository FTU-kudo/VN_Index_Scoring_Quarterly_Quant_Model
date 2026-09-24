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
3. **Thu thập dữ liệu tự động & thực tế**: Tích hợp trực tiếp với API `vnstock` thế hệ mới (`Quote`, `Listing`) và `yfinance`.
4. **Tự động hóa 100%**: Sẵn sàng với CI/CD GitHub Actions chạy tự động vào đầu mỗi quý và tự động Deploy Báo cáo HTML lên GitHub Pages.
5. **Kiểm định thực nghiệm nghiêm ngặt (Backtest & WFV)**: Áp dụng phương pháp Walk-Forward Validation (WFV) trượt tránh rò rỉ thông tin tương lai. Mô hình đã được backtest thành công trên **23 quý liên tiếp (Q1/2021 đến Q3/2026)**.

---

## ✨ CÁC TÍNH NĂNG NỔI BẬT GẦN ĐÂY (LATEST UPDATES)
- **Minh bạch hóa Dữ liệu (No Hallucination)**: Các biến số định lượng khi thiếu hụt dữ liệu (VD: OMO, ADTV) sẽ được gắn cờ đỏ `<MISSING>` trong báo cáo HTML thay vì âm thầm sử dụng giá trị default, đảm bảo quỹ đầu tư nhận diện chính xác chất lượng tín hiệu.
- **Báo cáo VAR Granger Causality Mở rộng**: Tích hợp p-value chi tiết của từng biến vĩ mô dẫn dắt VN-Index, cung cấp góc nhìn kinh tế lượng sâu sắc.
- **Khắc phục Data Leakage (Nhân bản dữ liệu P/E Median)**: Chuyển đổi kiến trúc tính toán sang `ticker_history.parquet`, hiển thị cả *Headline P/E* và *Median P/E* nhằm nhận diện chính xác các nhịp kéo trụ Mega-Cap (ví dụ: nhóm VIC).
- **Từ điển Biến số (Glossary & Rationale)**: Đã tích hợp Tab từ điển riêng trong UI báo cáo, giải thích chi tiết logic kinh tế của từng thông số (Δ VN1Y, Δ DXY, USD/VND...).

---

## 📐 SÁU TRỤ CỘT ĐỊNH LƯỢNG (6 PILLARS & COMPOSITE SCORING)

Hệ thống đánh giá thị trường dựa trên thang điểm chuẩn hóa **100 điểm**, phân bổ trọng số theo 6 nhóm biến số. Đây là bộ trọng số **duy nhất** (Single Source of Truth), được định nghĩa tại [`src/utils/config.py`](src/utils/config.py):

| # | Trụ cột | Trọng số | Các chỉ báo chính | Ghi chú |
|---|---------|:--------:|---------------------|---------|
| 1 | **Macro & Monetary** | **25%** | VN1Y Yield, ΔIR, USD/VND Z-score, M2 YoY, VN10Y Yield, Yield Spread | Môi trường lãi suất & tiền tệ |
| 2 | **Global & Intermarket** | **20%** | DXY Z-score, US10Y Yield, Net Foreign Flow Z-score | Áp lực toàn cầu & dòng vốn ngoại |
| 3 | **Valuation & Leverage** | **20%** | P/E Z-score 5Y, P/B Z-score 5Y, Margin Risk, Earnings Yield Gap | Định giá tương đối & rủi ro đòn bẩy |
| 4 | **Quant Model (MLR + VAR)** | **15%** | MLR predicted return, VAR T+5 forecast, Adj-R², Granger leaders | Tín hiệu từ mô hình kinh tế lượng |
| 5 | **ML Forecast** | **10%** | XGBoost WFV accuracy, F1-score, directional prediction | Tín hiệu Machine Learning |
| 6 | **Market Structure & FTSE** | **10%** | FTSE upgrade status, rebalancing proximity, ADTV change | Cấu trúc vi mô & nâng hạng |

> **⚠️ Lưu ý về phương pháp luận (Methodology Notes):**
> - **Hệ số quy đổi**: Các hàm chuyển đổi raw → score 0-100 (ví dụ: `vn1y_score = 100 - (vn1y-1.0)*14.0`, `mlr_score = 50 + pred*3000`) là heuristics được calibrate theo expert judgment. Hướng cải tiến: chuyển sang percentile rank thực tế trên cửa sổ expanding/rolling.
> - **Chỉ báo kỹ thuật ngắn hạn**: Một số indicators (RSI-14, MACD daily) có chu kỳ ngắn hơn đáng kể so với tần suất ra quyết định hàng quý (3 tháng). Hệ thống sử dụng giá trị snapshot tại thời điểm chấm điểm — đây là trade-off có chủ đích giữa tính kịp thời (timeliness) và tính ổn định (stability).
> - **Most Divergent Pillar**: Trường `most_divergent_pillar` trong output là nhóm có raw score lệch xa 50 nhất — đây là heuristic đơn giản, KHÔNG phải kết quả từ Granger Causality test. Granger tests được dùng riêng trong mô hình VAR để xếp hạng biến giải thích.

---

## 🔬 MÔ HÌNH KINH TẾ LƯỢNG & MACHINE LEARNING

Hệ thống kết hợp ba tầng mô hình phân tích định lượng:

### 1. Mô hình Hồi quy Đa biến (Multi-Linear Regression - MLR)
Thiết lập phương trình dự báo lợi suất VN-Index chu kỳ tiếp theo $R_{t+h}$:

$$
R_{t+h} = \alpha + \beta_1 \Delta \text{VN1Y}_t + \beta_2 \Delta \text{US10Y}_t + \beta_3 \Delta \text{DXY}_t + \beta_4 \text{NFF}_t + \beta_5 \text{PE-Zscore}_t + \beta_6 \Delta \text{Margin}_t + \beta_7 \Delta \text{USD/JPY}_t + \epsilon_t
$$
- **Newey-West HAC Standard Errors**: Tự động hiệu chỉnh sai số nhằm giải quyết hiện tượng phương sai thay đổi (Heteroskedasticity) và tự tương quan (Autocorrelation).
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

## ⚡ CƠ CHẾ ĐỘT PHÁ: RỔ VN30 ĐỘNG (DYNAMIC VN30 RETRIEVAL)

> **Vấn đề thực tế**: Rổ chỉ số VN30 được HOSE định kỳ tái cơ cấu 2 lần mỗi năm (vào tháng 1 và tháng 7). Nếu hardcode danh sách mã cổ phiếu trong mã nguồn, mô hình sẽ tính toán sai dòng tiền ngoại và độ rộng thị trường khi có các cổ phiếu bị loại bỏ hoặc thêm mới (ví dụ: NVL, REE, BVH, POW... đã được thay thế bởi BSR, GVR, LPB, MCH, TCX, VPL...).

**Giải pháp của hệ thống**:
- Xây dựng hàm [`get_vn30_tickers()`](src/utils/config.py) truy vấn trực tiếp từ API HOSE qua `vnstock.api.listing.Listing().symbols_by_group('VN30')`.
- Tự động lưu cache JSON tại `data/raw/vn30_tickers.json` kèm metadata thời gian cập nhật.
- Cơ chế Fallback 2 lớp: Tự động dùng cache gần nhất nếu mạng bị ngắt kết nối, và fallback về snapshot chính xác của HOSE nếu khởi tạo lần đầu khi offline.

---

## 🎖️ THANG ĐIỂM & MA TRẬN PHÂN BỔ TÀI SẢN (ASSET ALLOCATION MATRIX)

Dựa trên điểm số tổng hợp (0 - 100), hệ thống tự động đưa ra khuyến nghị phân bổ tài sản chiến lược:

| Khoảng Điểm | Xếp Hạng Khuyến Nghị | Tỷ Trọng Cổ Phiếu (% NAV) | Tỷ Trọng Tiền Mặt / Trái Phiếu | Chiến Lược Quản Trị Rủi Ro |
|:---:|:---:|:---:|:---:|---|
| **80 – 100** | 🟢 **RẤT HẤP DẪN (STRONG BUY)** | 85% – 100% | 0% – 15% | • Full vị thế cổ phiếu dẫn dắt (VN30)<br>• Cân nhắc sử dụng Margin chọn lọc |
| **65 – 79** | 🟡 **HẤP DẪN (BUY / ACCUMULATE)** | 70% – 85% | 15% – 30% | • Tích lũy cổ phiếu cơ bản tốt khi có điều chỉnh<br>• Duy trì đòn bẩy an toàn |
| **50 – 64** | ⚪ **TRUNG LẬP (NEUTRAL)** | 40% – 60% | 40% – 60% | • Cân bằng danh mục, tập trung cổ phiếu trả cổ tức cao<br>• Tuyệt đối không dùng margin cao |
| **35 – 49** | 🟠 **KÉM HẤP DẪN (CAUTIOUS / REDUCE)** | 20% – 40% | 60% – 80% | • Hạ tỷ trọng cổ phiếu beta cao<br>• Đưa margin về 0, chốt lời từng phần |
| **0 – 34** | 🔴 **TIÊU CỰC (DEFENSIVE / CASH)** | 0% – 20% | 80% – 100% | • Giữ tối đa tiền mặt / chứng chỉ tiền gửi<br>• Mở vị thế short phái sinh VN30F để hedge |

---

<!-- AUTO_RESULTS_START -->
## 📊 KẾT QUẢ THỰC NGHIỆM MẪU (AUTO-GENERATED)

> **⚠️ Section này được tạo TỰ ĐỘNG bởi `scripts/update_readme_results.py` từ dữ liệu output thực tế.**
> **Không chỉnh sửa thủ công — sẽ bị ghi đè khi chạy pipeline.**

```text
======================================================================
     VN-INDEX QUANTITATIVE SCORING — 2026-Q4
     Generated: 2026-09-24T22:54:32.873026
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
  • XGBoost Accuracy       : N/A
  • N Folds (WFV)          : N/A
  • Latest Prediction      : N/A

[COMPOSITE SCORE & ALLOCATION]
  • Total Score            : 53.76 / 100
  • Classification         : 🟡 HOLD — Neutral — Await confirming signals

[GROUP BREAKDOWN]
  • macro_monetary                : raw=  56.9  weight=14.23
  • global_intermarket            : raw=  37.8  weight=7.56
  • valuation_leverage            : raw=  57.2  weight=11.43
  • quant_model                   : raw=  61.0  weight=9.15
  • ml_forecast                   : raw=  50.0  weight=5.0
  • market_structure              : raw=  63.9  weight=6.39
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
│       └── validate_data.yml       # CI/CD: Kiểm định dữ liệu hàng ngày (Thứ 2 - Thứ 6)
├── data/
│   ├── raw/                       # Chứa cache dữ liệu thô (vn30_tickers.json, macro_sbv.csv)
│   ├── processed/                 # Dữ liệu sạch đã căn chỉnh mốc thời gian
│   └── features/                  # Ma trận đặc trưng 4 nhóm biến số
├── output/
│   ├── exports/                   # Tệp JSON xuất kết quả điểm số (live_score_2026_Q3.json)
│   ├── reports/                   # Báo cáo phân tích HTML / Markdown hoàn chỉnh
│   └── charts/                    # Biểu đồ phân rã điểm số và hàm phản ứng xung
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
│   │   ├── quarterly_scorer.py    # Bộ tính điểm tổng hợp 100 điểm & phân hạng
│   │   └── backtester.py          # Kiểm định chiến lược phân bổ tài sản lịch sử
│   ├── reporting/
│   │   └── report_builder.py      # Tạo báo cáo Executive Dashboard (HTML + CSS)
│   └── utils/
│       └── config.py              # Cấu hình trung tâm + get_vn30_tickers() động
├── .env.example                   # Mẫu cấu hình API key (VNSTOCK_API_KEY, Telegram, SMTP)
├── .gitignore                     # Đã cấu hình loại trừ file nhạy cảm và handoff notes
├── LICENSE                        # Giấy phép mã nguồn mở GNU AGPL v3.0
├── requirements.txt               # Danh sách gói phụ thuộc tương thích Python 3.11 - 3.14
├── live_scoring_Q3_2026.py        # Script chạy độc lập toàn diện nhanh (20 - 30 giây)
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

#### Cách 1: Chạy Siêu Tốc với Script Độc Lập (`live_scoring_Q3_2026.py`)
Script độc lập nạp dữ liệu trực tiếp từ API, tính toán toàn bộ 4 trụ cột, chạy hồi quy OLS và XGBoost Walk-Forward Validation chỉ trong **20 - 30 giây**:
```bash
python -X utf8 live_scoring_Q3_2026.py
```
*Kết quả điểm số sẽ được in ra console và tự động lưu tại `output/exports/live_score_2026_Q3.json`.*

#### Cách 2: Chạy Full Pipeline Theo Quý (`run_quarterly.py`)
```bash
# Chạy chấm điểm cho quý hiện tại:
python run_quarterly.py --quarter 2026-Q3

# Các tùy chọn nâng cao:
python run_quarterly.py --quarter 2026-Q3 --no-cache      # Buộc tải lại toàn bộ dữ liệu mới nhất
python run_quarterly.py --quarter 2026-Q3 --skip-ml       # Bỏ qua bước huấn luyện ML để kiểm tra nhanh
```

#### Cách 3: Chạy Cập nhật Tín hiệu Hàng ngày (`run_daily_update.py`)
Dùng sau 16:05 ICT mỗi ngày giao dịch để kiểm tra diễn biến giá, dòng tiền khối ngoại và cảnh báo biến động bất thường:
```bash
python run_daily_update.py
```

---

## 🤖 TỰ ĐỘNG HÓA CI/CD (GITHUB ACTIONS)

Dự án tích hợp sẵn 3 workflows tự động trong `.github/workflows/`:
1. **`quarterly_scoring.yml`**:
   - Tự động kích hoạt vào lúc 09:00 ICT ngày đầu tiên của mỗi quý (ngày 1 các tháng 1, 4, 7, 10).
   - Tự động fetch dữ liệu, tính điểm composite, xuất báo cáo HTML và lưu trữ Artifacts trên GitHub.
   - Hỗ trợ kích hoạt thủ công qua nút **Run workflow** trên giao diện GitHub Actions (`workflow_dispatch`).
2. **`deploy_pages.yml`**:
   - Tự động publish toàn bộ thư mục `output/reports` lên Internet thông qua **GitHub Pages** mỗi khi có commit mới vào nhánh main, giúp nhà quản lý quỹ xem báo cáo mọi lúc mọi nơi.
3. **`validate_data.yml`**:
   - Tự động kiểm tra chất lượng kết nối API và tính toàn vẹn dữ liệu từ Thứ 2 đến Thứ 6 hàng tuần.

---

## ⚖️ GIẤY PHÉP (LICENSE)

Dự án được phân phối dưới giấy phép **GNU Affero General Public License v3.0 (AGPL-3.0)**. Xem chi tiết tại tệp [LICENSE](LICENSE).

---

## ⚠️ TUYÊN BỐ MIỄN TRỪ TRÁCH NHIỆM (DISCLAIMER)

> Hệ thống phân tích định lượng này được xây dựng cho mục đích **nghiên cứu học thuật, phân tích kinh tế lượng và kiểm nghiệm mô hình đầu tư**.
> Mọi số liệu, xếp hạng điểm số và ma trận phân bổ tài sản do mô hình xuất ra không cấu thành lời mời chào hay khuyến nghị mua/bán bất kỳ chứng khoán cụ thể nào. Nhà đầu tư chịu trách nhiệm hoàn toàn đối với các quyết định đầu tư và quản trị rủi ro vốn của chính mình.
