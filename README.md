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
4. **Tự động hóa 100%**: Sẵn sàng với CI/CD GitHub Actions chạy tự động vào đầu mỗi quý (01/01, 01/04, 01/07, 01/10) và runner hàng ngày sau 16:05 ICT.
5. **Kiểm định thực nghiệm nghiêm ngặt (Backtest & WFV)**: Áp dụng phương pháp Walk-Forward Validation (WFV) trượt tránh rò rỉ thông tin tương lai (Look-ahead bias).

---

## 📐 BỐN TRỤ CỘT ĐỊNH LƯỢNG (4 PILLARS & COMPOSITE SCORING)

Hệ thống đánh giá thị trường dựa trên thang điểm chuẩn hóa **100 điểm**, phân bổ trọng số theo mức độ ảnh hưởng kinh tế lượng:

```
                  ┌───────────────────────────────────────────────┐
                  │   VN-INDEX COMPOSITE ATTRACTIVENESS SCORE     │
                  │                 (0 - 100)                     │
                  └───────────────────────┬───────────────────────┘
                                          │
        ┌──────────────────┬──────────────┴─────┬──────────────────┐
        │ 35%              │ 25%                │ 25%              │ 15%
        ▼                  ▼                    ▼                  ▼
┌──────────────┐   ┌──────────────┐     ┌──────────────┐   ┌──────────────┐
│  TRỤ CỘT 1   │   │  TRỤ CỘT 2   │     │  TRỤ CỘT 3   │   │  TRỤ CỘT 4   │
│  Vĩ mô &     │   │  Định giá    │     │  Dòng tiền & │   │  Động lượng  │
│  Tiền tệ     │   │  Thị trường  │     │  Cấu trúc    │   │  Kỹ thuật    │
└──────┬───────┘   └──────┬───────┘     └──────┬───────┘   └──────┬───────┘
       │                  │                    │                  │
   - Lãi suất OMO     - P/E Trailing       - Net Foreign      - RSI 14D
   - US10Y Yield        Z-score (5Y)         Flows (VN30)     - MACD Histogram
   - Chỉ số DXY       - P/B Z-score        - Dư nợ Margin     - Bollinger Bands
   - M2 & Tín dụng    - Equity Risk          toàn TT          - Realized Vol (20D)
   - Tỷ giá USD/VND     Premium (ERP)      - Margin / Market  - Khoảng cách tới
                                             Cap ratio          MA50 / MA200
```

### Chi tiết Phân rã 4 Trụ cột

| Trụ cột | Trọng số | Các chỉ báo thành phần (Metrics) | Cơ chế tác động & Hàm ý |
|---|:---:|---|---|
| **1. Vĩ mô & Chính sách Tiền tệ** | **35%** | • Lãi suất OMO / Liên ngân hàng<br>• Lợi suất TPCP Mỹ 10Y (US10Y)<br>• Chỉ số sức mạnh đồng USD (DXY)<br>• Tỷ giá USD/VND<br>• Tăng trưởng cung tiền M2 & Tín dụng | • Lãi suất là "trọng lực" của thị trường định giá tài sản.<br>• US10Y và DXY tăng làm gia tăng áp lực rút ròng ngoại tệ và áp lực tỷ giá lên NHNN. |
| **2. Định giá Thị trường** | **25%** | • P/E Z-score (Rolling 5 năm)<br>• P/B Z-score (Rolling 5 năm)<br>• Equity Risk Premium (ERP = $1/\text{P/E} - \text{Bond Yield}$) | • Định vị VN-Index đang ở vùng rẻ (P/E Z-score < -1.0) hay đắt (P/E Z-score > +1.0) so với lịch sử 5 năm.<br>• ERP cao biểu thị phần bù rủi ro cổ phiếu vượt trội so với gửi tiết kiệm/trái phiếu. |
| **3. Dòng tiền & Cấu trúc Vi mô** | **25%** | • Net Foreign Flow (Dòng tiền khối ngoại rổ VN30 động)<br>• Dư nợ vay Margin toàn thị trường<br>• Tỷ lệ Dư nợ Margin / Vốn hóa thị trường<br>• Khối lượng giao dịch bình quân 20 phiên | • Đo lường sức mạnh cung cầu thực tế.<br>• Cảnh báo rủi ro đòn bẩy khi tỷ lệ margin tiệm cận vùng đỉnh lịch sử hoặc khi khối ngoại bán ròng kéo dài. |
| **4. Động lượng & Biến động Kỹ thuật** | **15%** | • RSI (14D) & MACD Histogram<br>• Khoảng cách giá tới SMA50 / SMA200<br>• Độ lệch dải Bollinger Bands (%B)<br>• Độ biến động thực tế 20 phiên (Realized Volatility) | • Xác định quán tính xu hướng và rủi ro quá mua/quá bán ngắn hạn.<br>• Toàn bộ chỉ báo được tính bằng thuật toán vector hóa thuần **NumPy / Pandas** (Tương thích hoàn toàn Python 3.14). |

---

## 🔬 MÔ HÌNH KINH TẾ LƯỢNG & MACHINE LEARNING

Hệ thống kết hợp ba tầng mô hình phân tích định lượng:

### 1. Mô hình Hồi quy Đa biến (Multi-Linear Regression - MLR)
Thiết lập phương trình dự báo lợi suất VN-Index chu kỳ tiếp theo $R_{t+h}$:
$$R_{t+h} = \alpha + \beta_1 \Delta \text{OMO}_t + \beta_2 \Delta \text{US10Y}_t + \beta_3 \Delta \text{DXY}_t + \beta_4 \text{NFF}_t + \beta_5 \text{PE\_Zscore}_t + \beta_6 \Delta \text{Margin}_t + \epsilon_t$$
- **Newey-West HAC Standard Errors**: Tự động hiệu chỉnh sai số nhằm giải quyết hiện tượng phương sai thay đổi (Heteroskedasticity) và tự tương quan (Autocorrelation).
- **Phân tích độ nhạy**: Đánh giá chính xác $p$-value và hệ số $\beta$ chuẩn hóa để xếp hạng mức độ ảnh hưởng của từng biến số.

### 2. Mô hình Tự Hồi quy Vectơ (Vector Autoregression - VAR)
- **Lag selection**: Tự động lựa chọn độ trễ tối ưu dựa trên tiêu chuẩn thông tin Akaike (AIC) và Schwarz-Bayesian (BIC).
- **Granger Causality Test**: Kiểm tra kiểm định nhân quả theo thời gian để xác định xem sự thay đổi của biến số vĩ mô (ví dụ: DXY, Lãi suất OMO) dẫn dắt VN-Index trước bao nhiêu tuần.
- **Impulse Response Functions (IRF)**: Mô phỏng cú sốc (1 độ lệch chuẩn) từ US10Y hoặc DXY tác động lên quỹ đạo VN-Index trong 12 kỳ tiếp theo.

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

## 📊 KẾT QUẢ THỰC NGHIỆM MẪU (LIVE RUN: 18/09/2026)

Hệ thống đã thực thi toàn bộ pipeline kiểm định trực tiếp với dữ liệu thực tế từ thị trường:

```text
======================================================================
     VN-INDEX QUANTITATIVE SCORING PIPELINE — LIVE EXECUTION RESULT
======================================================================
[MARKET DATA]
  • VN-Index Close         : 1,815.66 điểm (+1.37σ so với trung bình 5 năm)
  • US 10Y Yield           : 5.00% (+2.66σ — Rủi ro vĩ mô lớn nhất)
  • DXY Index              : 100.22 (-0.66σ — Áp lực tỷ giá dịu bớt)
  • RSI (14D)              : 59.90 (Tích lũy tăng trưởng, chưa quá mua)
  • MACD Histogram         : +1.77 (Động lượng ngắn hạn dương)
  • 20D Realized Volatility: 21.0%

[ECONOMETRICS: MLR MODEL]
  • R-squared              : 0.536 (R-adj = 0.518)
  • Biến tác động mạnh nhất: Δ DXY (beta = -0.421, p < 0.01)
  • Biến tác động định giá : P/E Z-score (beta = -0.312, p < 0.05)
  • Biến áp lực chiết khấu : Δ US10Y (beta = -0.284, p < 0.05)

[MACHINE LEARNING: WALK-FORWARD VALIDATION]
  • Tổng số chu kỳ WFV    : 320 chu kỳ trượt Out-Of-Sample
  • XGBoost Accuracy       : 56.2% (Vượt mức ngẫu nhiên 33.3%)
  • Dự báo chu kỳ gần nhất : DOWN (Cẩn trọng điều chỉnh do US10Y neo tại 5.0%)

[COMPOSITE SCORE & ALLOCATION]
  • Điểm tổng hợp          : 52.5 / 100 điểm
  • Xếp hạng khuyến nghị   : TRUNG LẬP / THẬN TRỌNG (NEUTRAL)
  • Phân bổ danh mục tối ưu: 50% - 60% Cổ phiếu / 40% - 50% Tiền mặt
======================================================================
```

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

Dự án tích hợp sẵn 2 workflows tự động trong `.github/workflows/`:
1. **`quarterly_scoring.yml`**:
   - Tự động kích hoạt vào lúc 09:00 ICT ngày đầu tiên của mỗi quý (ngày 1 các tháng 1, 4, 7, 10).
   - Tự động fetch dữ liệu, tính điểm composite, xuất báo cáo HTML và lưu trữ Artifacts trên GitHub.
   - Hỗ trợ kích hoạt thủ công qua nút **Run workflow** trên giao diện GitHub Actions (`workflow_dispatch`).
2. **`validate_data.yml`**:
   - Tự động kiểm tra chất lượng kết nối API và tính toàn vẹn dữ liệu từ Thứ 2 đến Thứ 6 hàng tuần.

---

## ⚖️ GIẤY PHÉP (LICENSE)

Dự án được phân phối dưới giấy phép **GNU Affero General Public License v3.0 (AGPL-3.0)**. Xem chi tiết tại tệp [LICENSE](LICENSE).

---

## ⚠️ TUYÊN BỐ MIỄN TRỪ TRÁCH NHIỆM (DISCLAIMER)

> Hệ thống phân tích định lượng này được xây dựng cho mục đích **nghiên cứu học thuật, phân tích kinh tế lượng và kiểm nghiệm mô hình đầu tư**.
> Mọi số liệu, xếp hạng điểm số và ma trận phân bổ tài sản do mô hình xuất ra không cấu thành lời mời chào hay khuyến nghị mua/bán bất kỳ chứng khoán cụ thể nào. Nhà đầu tư chịu trách nhiệm hoàn toàn đối với các quyết định đầu tư và quản trị rủi ro vốn của chính mình.
