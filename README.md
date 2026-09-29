# 📊 VN-Index Quarterly Quantitative Scoring Model
### Comprehensive Quantitative System for Scoring the Vietnamese Stock Market Every Quarter
### Hệ Thống Định Lượng Toàn Diện Đánh Giá & Chấm Điểm Thị Trường Chứng Khoán Việt Nam Đầu Mỗi Quý

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Market](https://img.shields.io/badge/Market-Vietnam%20(HOSE%20%7C%20HNX%20%7C%20UPCOM)-success.svg)]()
[![Framework](https://img.shields.io/badge/Framework-Econometrics%20%2B%20Machine%20Learning-orange.svg)]()
[![Automation](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions%20Scheduled-brightgreen.svg)]()

**🌐 Language / Ngôn ngữ:** **[🇬🇧 English](#english)** · **[🇻🇳 Tiếng Việt](#tieng-viet)**

*The web reports default to English with a Vietnamese toggle (🇻🇳 VI button) — this README is bilingual to match.*

---

<a id="english"></a>
## 🇬🇧 ENGLISH

## 🎯 EXECUTIVE OVERVIEW

**VN_Index_Scoring_Quarterly_Quant_Model** is a fund-manager-grade (CFA charterholder level) quantitative finance system built to answer one core question:

> *"On the first trading day of each financial quarter, where is the Vietnamese stock market (VN-Index) in its cycle? How attractive is it as an investment, on a 100-point scale? How should a fund allocate assets to maximize the Sharpe Ratio and protect the portfolio from major drawdowns?"*

The system is engineered to fully meet **5 Gold Standards**:
1. **Comprehensive variable coverage**: 4 quantitative pillars integrated (Macro & Monetary, Historical Valuation, Flows & Margin, Technical Momentum).
2. **Rigorous quantification**: Multi-Linear Regression (MLR with Newey-West HAC robust errors), Vector Autoregression (VAR with Granger Causality & IRF), and Machine Learning (XGBoost / Random Forest).
3. **Automated, real-world data**: Direct integration with the new-generation `vnstock` API (`Quote`, `Listing`) and the VNDirect API.
4. **100% automation**: CI/CD via GitHub Actions runs automatically at the start of every quarter and deploys HTML reports to GitHub Pages.
5. **Strict empirical validation (Backtest & WFV)**: Walk-Forward Validation (WFV) with a rolling scheme that avoids future-information leakage (data leakage). The model has been successfully backtested on **24 consecutive quarters (Q1/2021 to Q4/2026)**.

---

## 📐 SIX QUANTITATIVE PILLARS & COMPOSITE SCORING

The system scores the market on a normalized **100-point scale**, weighted across 6 variable groups. These are the **single source of truth** weights, defined in [`src/utils/config.py`](src/utils/config.py):

| # | Pillar | Weight | Key indicators | Notes |
|---|---------|:--------:|---------------------|---------|
| 1 | **Macro & Monetary** | **25%** | VN1Y Yield, ΔIR, USD/VND Z-score, M2 YoY, VN10Y Yield, Yield Spread | Rate & monetary environment |
| 2 | **Global & Intermarket** | **20%** | DXY Z-score, US10Y Yield, USD/JPY Z-score, Net Foreign Flow Z-score | Global pressure & foreign capital flows |
| 3 | **Valuation & Leverage** | **20%** | P/E Z-score 5Y, P/B Z-score 5Y, Margin Risk, Earnings Yield Gap | Relative valuation & leverage risk |
| 4 | **Quant Model (MLR + VAR)** | **15%** | MLR predicted return, VAR T+5 forecast, Adj-R², Granger leaders | Signals from econometric models |
| 5 | **ML Forecast** | **10%** | XGBoost WFV accuracy, F1-score, directional prediction | Machine Learning signals |
| 6 | **Market Structure & FTSE** | **10%** | FTSE upgrade status, rebalancing proximity, ADTV change | Microstructure & index upgrades |

> **⚠️ Methodology Notes:**
> - **Point-in-time at quarter start (buy-side principle)**: Allocation decisions are made on the first trading day of the quarter, so quarter Q's score is computed only from data available through the last session of quarter Q-1 — applied **consistently to both live runs and historical backfills** (see `src/utils/dates.py`). At that cut-off, `*_q_ytd` columns hold the full cumulative value of the quarter that just ended. The `data_as_of` field in every JSON export lets you audit exactly which date the score was computed as of. Mid-quarter monitoring runs use `--as-of YYYY-MM-DD` and are flagged `point_in_time=false` so they never leak into backtests.
> - **Conversion coefficients (anti-signal-compression)**: The raw → 0-100 score mapping functions (e.g. `vn1y_score = 100 - (vn1y-1.0)*14.0`) are heuristics calibrated by expert judgment. Model signals use strong gains so they are not crushed: `mlr_score = 50 + pred*20000` (±0.10%/day → 70/30), `var_score = 50 + pred*5000`. MISSING signals (MLR/VAR/ADTV/ETF) **do not join the pillar average** — the average is renormalized over the signals that actually exist, instead of a neutral-50 fallback dragging everything toward the middle.
> - **Short-horizon technical indicators**: Some indicators (RSI-14, daily MACD) have significantly shorter cycles than the quarterly decision frequency (3 months). The system uses their snapshot value at scoring time — a deliberate trade-off between timeliness and stability.
> - **Most Divergent Pillar**: The `most_divergent_pillar` output field is simply the group whose raw score is farthest from 50 — a plain heuristic, NOT a Granger Causality result. Granger tests are used separately inside the VAR model to rank explanatory variables.

---

## 🎚️ TWO-TIER SCORING: RAW COMPOSITE + CALIBRATED ACTION SIGNAL

The system uses a **two-tier scoring architecture** to fix "chronic HOLD" (22/24 quarters labeled HOLD because raw scores were compressed into the narrow 45.8–61.4 band — useless for asset allocation):

| Tier | Name | Formula | Role |
|:---:|---|---|---|
| **1** | **Raw Composite** (`total_score`) | 6 pillars × weights, 0–100 scale | **Reference** tier — stable across all periods, for historical comparison & backtest |
| **2** | **Calibrated Action Signal** (`calibrated_score`) | `clip(50 + 15 × z, 0, 100)` where `z = (total − μ_hist)/σ_hist` over an **expanding window of PRIOR quarters only** (point-in-time, no look-ahead) | **Action** tier — asset-allocation labels (BUY/ACCUMULATE/HOLD/REDUCE/SELL) |

**Parameters** live in `config.py → SCORE_CALIBRATION` (single source of truth): `center=50`, `z_scale=15`, `min_history=4`, clip `[0, 100]`. The first quarter (< 4 quarters of history) or σ_hist ≈ 0 → **keep the raw score**, `calibration_applied=false`. Labels come from `get_score_label()` — the same threshold set as the raw tier.

**24-quarter backfill results (2021-Q1 → 2026-Q4)** — *after the real-data backfill of 09/2026 (ADTV, full-history bonds, M2 ADB/GSO, P/E-P/B-EYG Z-scores):*

| Label distribution | Before (raw) | After (calibrated) |
|---|:---:|:---:|
| 🟢 BUY | 0 | 0 |
| 🔵 ACCUMULATE | **1** | **1** |
| 🟡 HOLD | **19** | **6** |
| 🟠 REDUCE | **4** | **7** |
| 🔴 SELL | 0 | **10** |

The 2022 bear quarters and the 2026 period correctly fired defensive signals: **2022-Q2 = SELL (11.3)**, 2022-Q3 = REDUCE (46.8), **2022-Q4 = SELL (20.6)**, **2026-Q2 = SELL (17.4)**, live quarter **2026-Q4 = SELL (29.4)**; the very first decision **2021-Q1 = ACCUMULATE (68.6)** reflects the 2020 easing cycle (VN1Y 0.43%, M2 +14.5%) — even though the real flows z (−2.43: heavy foreign net selling in Q4/2020) pulled the global pillar down from 63.2 → 55.9 versus the old default-50 era.

> **📈 ADTV data source (since 09/2026 — N/A eliminated for 24/24 quarters):** `ADTV change = ADTV(Q−1)/ADTV(Q−2) − 1` computed point-in-time from the `volume` column of the VN-Index OHLCV (vnstock, VCI source) — quarter Q's decision only uses the 2 **completed** quarters before it. ADTV score = `clip(50 + 100 × %change, 0, 100)`. Example: 2025-Q4 liquidity surge +65.7% QoQ → score 100; 2026-Q1 correction −38.4% → score 12. Full audit: `data/scores/vnindex_quarterly_adtv.json`.

> **📥 Backfill data sources 09/2026 — bonds + M2 + Z-scores (real sources, no guesswork):**
> - **Bonds (24/24 quarters with data)**: Nelson-Siegel fitted curve from the `VN_Bond_Yield_pipeline` repo — switched to the **full-history** build `fitted_curve_ns_full.json` (2012-08-06 → present, 3,397 days) instead of the dashboard cut starting 2022-09-22. VN1Y/ΔVN1Y/VN10Y/10Y−2Y spread taken as-of point-in-time; **pre-check: 68/68 recomputed values match exactly** for quarters that already had data. Fixes 7 quarters 2021-Q1→2022-Q3 that were N/A (VN1Y 0.43–1.82%, VN10Y 1.91–3.20%).
> - **M2 (24/24 quarters with data)**: ADB Key Indicators Database (SDMX `FM2_PTX_PS.VIE`, originally from SBV) 2000→2024 + GSO Socio-Economic Report Q4/2025 (broad money **+14.98%** as of 22/12/2025). Point-in-time via backward `merge_asof` — quarter Q's decision receives the most recent **published** year (2021-Q* ← 2020 = +14.53%, 2022-Q* ← 2021 = +10.66%, 2023-Q1/Q2 ← 2022 = +6.15% …). 2026 has no published figure yet → uses 2025. Committed fallback: `data/external/m2_credit_adb_gso.csv` (with per-number source notes).
> - **P/E-P/B-EYG Z-scores**: min_periods lowered from 2.5 years (630 sessions) to **252 sessions** (~1 year) because the ex-Vingroup P/E series only starts ~2020-12 (free-float share counts missing before that). First valid z 2021-12-20 → fixes pe_zscore for 6 quarters 2022-Q1→2023-Q2; **Z values on days with 2.5 years of data are unchanged** (pre-check 28/28 match). EYG = 1/PE − VN10Y is now correctly passed through `df_macro` — previously it **silently defaulted to 50 in all 24/24 quarters**.
> - Per-quarter real-input audit: `data/scores/vnindex_quarterly_market_data.json`.

> **🔄 Foreign flows (fixed 09/2026, wave 2 — flows N/A eliminated for 5 quarters 2021-Q1→2022-Q1):**
> - **Discovery while checking the VNDirect API** (`api-finfo.vndirect.com.vn/v4/foreigns`): `STOCK_HOSE`/`ETF_HOSE` data actually exists from **2018-08-30** (588 sessions before 2021-01) — the "API only from 2021" limit in the fetcher was self-imposed, not the API's. Removed → quarterly flows series starts 2018-Q4 → **all 24 decision quarters have real z-scores** (previously the first 5 were N/A default 50).
> - **Silent bug fixed alongside**: the PE/PB dataset only has complete share counts from 2021-04-15; before that total_mc ≈ 11 trillion VND (26–142 tickers, ~300× off) → quarter 2021-Q1 inside the expanding stats of EVERY stored flows z was blown up (q_ytd up to ~250% of MC). Fix: **splice published HOSE market cap** (data/external/hose_market_cap_published.csv — 2018-2020 anchors as reported by HOSE, linear interpolation; real MC from 2021-04-15). z for 2022+ quarters recomputed with a longer, cleaner expanding window.
> - Backfill pre-check: recomputed q_ytd (% of market cap) must match the stored series for every quarter with data; every quarter must have a z — any mismatch STOPS the run. Per-quarter input audit: `data/scores/vnindex_quarterly_flows.json`.
> - Real-data smoke test (verified 09/2026): Q4/2020 HOSE foreign net sold −15,070 bn VND (−0.44% of MC) → z = **−2.03** for the 2021-Q1 decision (previously default 50).

> **🚧 Remaining N/A after the 09/2026 backfill — REAL data limits, deliberately left unfilled:**
> - `pe_zscore` / `pb_zscore` / `eyg_zscore`: **4 quarters 2021-Q1→Q4**. The ex-Vingroup P/E-P/B series (computed from market cap = price × free-float shares) only starts ~2020-12 in the PE_PB_HOSE_stocks dataset; 252 sessions are needed for a z-score → first z 2021-12-20, later than the as-of of every 2021 decision (latest 2021-09-30), so 2021-Q1→Q4 remain N/A; from the 2022-Q1 decision (as-of 2021-12-31) onward real z exists.
> - Principle: **missing data → neutral default 50 (or renormalize), no interpolation, no guesswork**. Every number in the exports is traceable to a published source.

> **⚠️ Honest signal-quality disclosure (rechecked after calibration v2, 2026-09-29):** the calibrated tier is a **relative regime/allocation signal, not a return forecast**. Strict point-in-time evaluation (signal at quarter t vs. the strict within-quarter forward return from the t−1 close to the outcome close of t, n=23): Spearman IC ≈ **0.34 calibrated / 0.19 raw**, sign hit-rate ≈ **56.5% / 47.8%**. Against *consecutive* quarter-over-quarter forward returns (t→t+1, n=22): IC ≈ **0.18 calibrated / −0.03 raw**, hit ≈ 50%. Directional power is modest — honesty, not marketing: the signal complements valuation/context, it does not predict quarterly returns reliably by itself. Tier 2's purpose is restoring **regime dispersion** for allocation sizing (previously 22/24 quarters "HOLD" made sizing impossible) while v2 guardrails prevent neutral raw scores from being auto-driven to the 0/100 rails. Full formula-verified backtest: `06_Signal_Efficacy` sheet in the master workbook.

---

## 🔬 ECONOMETRICS & MACHINE LEARNING MODELS

The system combines three layers of quantitative analysis:

### 1. Multi-Linear Regression (MLR)
Forecasting equation for the next-cycle VN-Index return $R_{t+h}$:

$$
R_{t+h} = \alpha + \beta_1 \Delta \text{VN1Y}_t + \beta_2 \Delta \text{US10Y}_t + \beta_3 \Delta \text{DXY}_t + \beta_4 \text{NFF}_t + \beta_5 \text{PE-Zscore}_t + \beta_6 \Delta \text{Margin}_t + \beta_7 \Delta \text{USD/JPY}_t + \epsilon_t
$$
- **Purely predictive (not nowcast)**: The dependent variable is the **average daily log-return over the next $h = 21$ sessions** ($t+1 \dots t+h$, ~1 trading month); regressors use only information known at the close of session $t$ — no same-day returns.
- **Newey-West HAC standard errors**: Automatically corrects for heteroskedasticity and autocorrelation; `maxlags ≥ h` to handle autocorrelation introduced by overlapping forward windows.
- **Out-of-sample evaluation**: The model is evaluated on the final 25% of data (holdout, no shuffle) with sign hit-rate and OOS R² — an honest measure of predictive power, separate from in-sample R².
- **Sensitivity analysis**: Exact $p$-values and standardized $\beta$ coefficients rank each variable's influence.

### 2. Vector Autoregression (VAR)
- **Lag selection**: Optimal lag order chosen automatically via Akaike (AIC) and Schwarz-Bayesian (BIC) information criteria.
- **Granger Causality Test**: Time-causality tests determine how many weeks macro variables (e.g. DXY, VN1Y yield, USD/JPY) lead the VN-Index.
- **Impulse Response Functions (IRF)**: Simulates a 1-standard-deviation shock from US10Y, DXY, or USD/JPY (Yen-carry-unwind effect) and traces its impact on the VN-Index path over the next 12 periods.

### 3. Machine Learning + Walk-Forward Validation (XGBoost + WFV)
- **Classifier structure**: 3-state market trend classification: `UP` (+1), `SIDEWAY` (0), `DOWN` (-1).
- **Walk-Forward Validation (WFV)**:
  - Rolling training window (250–500 sessions).
  - Fully out-of-sample (OOS) testing on subsequent cycles, eliminating 100% of look-ahead bias.
  - Feature Importance extracted and cross-checked against the econometric regression coefficients.

---

## 🎖️ SCORE BANDS & ASSET ALLOCATION MATRIX

The **single source of truth** thresholds from `config.py → SCORE_LABELS` (the `test_score_label_sync` test FAILS automatically if any code hardcodes the thresholds again). Applied to **both tiers** — the actual action label comes from the calibrated tier:

| Score Band | Recommendation | Dashboard/Excel Color | Equity Weight (% NAV) | Cash / Bonds | Risk Management Strategy |
|:---:|:---:|:---:|:---:|:---:|---|
| **80 – 100** | 🟢 **BUY** | 🟢 Green `#10b981` | 85% – 100% | 0% – 15% | • Full position in leading stocks (VN30)<br>• Consider selective margin use |
| **65 – 79** | 🔵 **ACCUMULATE** | 🔵 Blue `#3b82f6` | 70% – 85% | 15% – 30% | • Accumulate quality stocks on dips<br>• Maintain safe leverage |
| **50 – 64** | 🟡 **HOLD** | 🟡 Yellow `#eab308` | 40% – 60% | 40% – 60% | • Rebalance portfolio toward high-dividend stocks<br>• Absolutely no heavy margin |
| **35 – 49** | 🟠 **REDUCE** | 🟠 Orange `#f97316` | 20% – 40% | 60% – 80% | • Cut high-beta exposure<br>• Bring margin to 0, take partial profits |
| **0 – 34** | 🔴 **SELL** | 🔴 Red `#ef4444` | 0% – 20% | 80% – 100% | • Maximum cash / deposit certificates<br>• Open VN30F derivative shorts as a hedge |

On the **24-quarter dashboard**, cards & timeline are colored by the **calibrated regime** (4–5 colors); the **raw composite** line stays **dashed** as reference. In **quarterly reports**, the hero shows the raw score + a prominent `⚡ ACTION: {calibrated_label} — {calibrated_score}` chip, and the Action Panel follows the calibrated tier (marker, allocation, z-diagnostics line: `z, μ_hist, σ_hist, n`).

---

<!-- AUTO_RESULTS_START -->
## 📊 SAMPLE RESULTS / KẾT QUẢ THỰC NGHIỆM MẪU (AUTO-GENERATED)

> **⚠️ This section is AUTO-GENERATED by `scripts/update_readme_results.py` from actual output data.**
> **Do not edit manually — it will be overwritten by the pipeline.**
> **⚠️ Section này được tạo TỰ ĐỘNG bởi `scripts/update_readme_results.py` từ dữ liệu output thực tế.**
> **Không chỉnh sửa thủ công — sẽ bị ghi đè khi chạy pipeline.**

```text
======================================================================
     VN-INDEX QUANTITATIVE SCORING — 2026-Q4
     Generated: 2026-09-29T16:26:46.191151
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
  • Total Score (raw)      : 47.67 / 100
  • Classification (raw)   : 🟠 REDUCE — Reduce exposure — Increasing pressure
  • Calibrated Action      : 🔴 SELL — 33.97 / 100 (0–20% Equities)
  • Calibration z          : -1.07

[GROUP BREAKDOWN]
  • macro_monetary                : raw=  57.9  weight=14.48
  • global_intermarket            : raw=  36.4  weight=7.28
  • valuation_leverage            : raw=  40.4  weight=8.08
  • quant_model                   : raw=  50.8  weight=7.63
  • ml_forecast                   : raw=  41.6  weight=4.16
  • market_structure              : raw=  60.4  weight=6.04
======================================================================
```
<!-- AUTO_RESULTS_END -->

---

## 📁 PROJECT REPOSITORY LAYOUT

```text
VN_Index_Scoring_Quarterly_Quant_Model/
├── .github/
│   └── workflows/
│       ├── quarterly_scoring.yml   # CI/CD: runs automatically at the start of each quarter (Jan/Apr/Jul/Oct 1)
│       ├── batch_scoring.yml       # CI/CD: full 24-quarter historical backtest scan
│       └── validate_data.yml       # CI/CD: daily data validation (Mon–Fri)
├── data/
│   ├── raw/                       # Raw data cache (vn30_tickers.json, macro_sbv.csv)
│   ├── processed/                 # Cleaned, time-aligned data
│   └── features/                  # Feature matrices for the 4 variable groups
├── output/
│   ├── exports/                   # Score JSON exports (score_*.json) + Excel Quant Factor Workbooks
│   ├── reports/                   # Full HTML analysis reports (index.html = 24-quarter dashboard)
│   └── charts/                    # Score-decomposition charts & impulse response functions
├── scripts/
│   ├── backfill_calibrated_scores.py  # Idempotent calibrated backfill for 24 quarters (parquet + JSON)
│   ├── rebuild_html.py            # Rebuild 24 HTML reports + dashboard + validate + Excel
│   ├── generate_excel_report.py   # Exports the 8-sheet Excel Quant Factor Workbook
│   ├── export_excel_detailed.py   # Exports the 20-sheet ultra-detailed data workbook (NA register)
│   ├── inject_vnindex_chart.py    # Validator: VN-Index overlay (fails loudly if missing)
│   └── inject_navbar.py           # Validator: navbar quarter navigation (fails loudly if missing)
├── src/
│   ├── data/
│   │   └── fetcher.py             # Data ingestion: vnstock 4.0.2 (Quote, Listing) & yfinance
│   ├── features/
│   │   ├── macro_features.py      # Pillar 1: rates, DXY, US10Y, FX, M2
│   │   ├── valuation_features.py  # Pillar 2: P/E, P/B Z-scores, ERP
│   │   ├── flow_features.py       # Pillar 3: VN30 net foreign flow, margin debt
│   │   ├── technical_features.py  # Pillar 4: RSI, MACD, BB, volatility (pure NumPy/Pandas)
│   │   └── global_features.py     # Global intermarket correlations
│   ├── models/
│   │   ├── regression/
│   │   │   └── mlr_model.py       # Multi-Linear Regression with Newey-West HAC
│   │   ├── var/
│   │   │   └── var_model.py       # Vector Autoregression + Granger Causality + IRF
│   │   └── ml/
│   │       └── ml_model.py        # XGBoost / Random Forest + Walk-Forward Validation
│   ├── scoring/
│   │   ├── quarterly_scorer.py    # Two-tier scorer: raw composite + calibrate_total_score() (Calibrated Action Signal)
│   │   └── backtester.py          # Historical asset-allocation strategy validation
│   ├── reporting/
│   │   ├── report_builder.py      # Two-tier HTML reports + dashboard + VN-Index overlay (integrated, not injected)
│   │   └── excel_builder.py       # 8-sheet Excel Quant Factor Workbook (CALIBRATED ACTION KPI)
│   └── utils/
│       └── config.py              # Central config: SCORE_LABELS + SCORE_CALIBRATION + dynamic get_vn30_tickers()
├── tests/
│   ├── conftest.py                # Test hygiene: SCORES_DIR isolation (pytest never touches production data/)
│   ├── test_score_calibration.py  # 13 tests: calibrated formula, clip, fallback, point-in-time, SSOT, gains
│   └── ...                        # MLR forecast, point-in-time dates, label sync, scoring weights
├── .env.example                   # API key config template (VNSTOCK_API_KEY, Telegram, SMTP)
├── .gitignore                     # Excludes sensitive files and handoff notes
├── LICENSE                        # GNU AGPL v3.0 open-source license
├── requirements.txt               # Dependencies compatible with Python 3.11 – 3.14
├── run_quarterly.py               # Official quarterly pipeline entrypoint
└── run_daily_update.py            # Daily post-close signal update entrypoint
```

---

## 🚀 QUICKSTART

### 1. Environment Requirements
- **Python**: `>= 3.11` (fully validated on **Python 3.14**).
- **OS**: Windows / macOS / Linux.

### 2. Install
```bash
git clone https://github.com/FTU-kudo/VN_Index_Scoring_Quarterly_Quant_Model.git
cd VN_Index_Scoring_Quarterly_Quant_Model

python -m venv .venv

# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure API Keys (`.env`)
```bash
cp .env.example .env     # Linux / macOS
copy .env.example .env   # Windows
```
Edit `.env` and add your vnstock API key:
```ini
VNSTOCK_API_KEY=your_vnstock_api_key
```

---

### 4. Operating the Model

#### Option 1: Full Quarterly Pipeline (`run_quarterly.py`)
```bash
# Score the current quarter:
python run_quarterly.py --quarter 2026-Q3

# Advanced options:
python run_quarterly.py --quarter 2026-Q3 --no-cache      # Force fresh data download
python run_quarterly.py --quarter 2026-Q3 --skip-ml       # Skip ML training for a quick check
```
The pipeline computes **both score tiers** (raw composite + calibrated action signal), writes `calibrated_score`/`calibrated_label` to `data/scores/quarterly_scores_history.parquet`, then auto-syncs the README + all HTML reports + Excel.

#### Option 2: Backfill the Calibrated Action Signal for history (`scripts/backfill_calibrated_scores.py`)
Idempotent — only **ADDS** calibrated columns/fields to the 24 historical quarters (parquet + all `output/exports/score_*.json`), **NEVER touches** raw scores; auto-drops the `2099-Q1` test row if it leaked into the parquet:
```bash
python scripts/backfill_calibrated_scores.py
# Prints a raw vs calibrated comparison table + label distribution per quarter
```

#### Option 3: Rebuild All HTML Reports + Dashboard + Excel (`scripts/rebuild_html.py`)
```bash
python scripts/rebuild_html.py
# 24 quarterly reports + root dashboard + VN-Index overlay & navbar validation
# (exit code != 0 if a feature is missing — fails loudly) + Excel workbook
```

#### Option 4: Export the Excel Quant Factor Workbook (`scripts/generate_excel_report.py`)
```bash
python scripts/generate_excel_report.py
# -> output/exports/VN_Index_Quant_Factor_Analysis.xlsx (8 sheets)
#    00_Dashboard: "CALIBRATED ACTION" KPI | 01_Score_History: calibrated column
#    06_Signal_Efficacy: backtest by calibrated signal (raw as reference)
```

#### Option 4b: Export the ULTRA-DETAILED Excel of all data (`scripts/export_excel_detailed.py`)
```bash
python scripts/export_excel_detailed.py
# -> output/exports/VN_Index_Detailed_Data_Export.xlsx (20 sheets, ~2,200 rows)
#    01_Summary / 02-03_Pillars: 24-quarter scores (RAW + calibrated + weighted)
#    04_Factor_Details: EVERY factor of EVERY quarter — original text + parsed score
#    05_Market_Inputs / 06_Flows_Audit / 07_ADTV: real per-quarter inputs
#      (NS bonds, M2 ADB/GSO, P/E-P/B-EYG z; flows z new vs old)
#    08_MLR / 09_Granger / 10-12_ML: regression + causality + walk-forward
#      per-fold + feature importance per quarter
#    13_Rationale / 14_Index_Prices / 15-16_External sources
#    17_NA_Register: N/A ledger — what was filled from which source,
#      what deliberately remains N/A (pe_zscore 2021 — real data limit)
# Test: tests/test_excel_detailed_export.py (13 tests — all 24 quarters, matches
# history parquet, flows z 24/24, honest N/A register)
```

#### Option 5: Daily Signal Update (`run_daily_update.py`)
Run after 16:05 UTC+7 (Vietnam time) on every trading day to check price action, foreign flows, and unusual-volatility alerts:
```bash
python run_daily_update.py
```

---

## 🤖 CI/CD AUTOMATION (GITHUB ACTIONS)

The project ships 4 automated workflows in `.github/workflows/`:
1. **`quarterly_scoring.yml`**:
   - Triggers automatically at 09:00 UTC+7 (Vietnam time) on the first day of each quarter (Jan 1, Apr 1, Jul 1, Oct 1).
   - Fetches data, computes the composite score, exports HTML reports, and stores Artifacts on GitHub.
   - Supports manual triggering via the **Run workflow** button in the GitHub Actions UI (`workflow_dispatch`).
2. **`batch_scoring.yml`**:
   - Runs the full 24-quarter historical backtest scan for large-scale recomputes, reporting all failures.
3. **`deploy_pages.yml`**:
   - Publishes the entire `output/reports` folder to the internet via **GitHub Pages** on every new commit to main, so fund managers can view reports anytime, anywhere.
4. **`validate_data.yml`**:
   - Automatically checks API connection quality and data integrity Monday through Friday.

---

## ⚖️ LICENSE

Distributed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**. See [LICENSE](LICENSE) for details.

---

## ⚠️ DISCLAIMER

> This quantitative analysis system is built for **academic research, econometric analysis, and investment-model validation**.
> All figures, score ratings, and asset-allocation matrices produced by the model do not constitute an offer or a recommendation to buy/sell any specific security. Investors bear full responsibility for their own investment decisions and capital risk management.

---
---

<a id="tieng-viet"></a>
## 🇻🇳 TIẾNG VIỆT

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
| 🟠 REDUCE | **4** | **7** |
| 🔴 SELL | 0 | **10** |

Các quý gấu 2022 và giai đoạn 2026 ra tín hiệu phòng thủ đúng: **2022-Q2 = SELL (11.3)**, 2022-Q3 = REDUCE (46.8), **2022-Q4 = SELL (20.6)**, **2026-Q2 = SELL (17.4)**, quý live **2026-Q4 = SELL (29.4)**; quyết định đầu tiên **2021-Q1 = ACCUMULATE (68.6)** phản ánh chu kỳ nới lỏng 2020 (VN1Y 0.43%, M2 +14.5%) — dù z flows thật (−2.43: khối ngoại bán ròng mạnh Q4/2020) đã kéo trụ cột global xuống từ 63.2 → 55.9 so với thời còn default 50.

*(Chi tiết nguồn dữ liệu backfill 09/2026 — ADTV, trái phiếu + M2 + Z-score, dòng tiền khối ngoại, N/A còn lại và báo cáo trung thực về chất lượng tín hiệu — xem phần 🇬🇧 English ở trên; nội dung hai ngôn ngữ tương đương 1-1.)*

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

**Kết quả thực nghiệm mẫu (auto-generated):** xem khối `📊 SAMPLE RESULTS / KẾT QUẢ THỰC NGHIỆM MẪU` trong phần 🇬🇧 English ở trên — script `scripts/update_readme_results.py` ghi đè khối này từ dữ liệu output thật (header song ngữ).

---

## 📁 CẤU TRÚC DỰ ÁN (PROJECT REPOSITORY LAYOUT)

*(Cây thư mục đầy đủ với chú thích tiếng Việt — bản tiếng Anh có ở phần 🇬🇧 English. Cấu trúc hai ngôn ngữ giống hệt nhau.)*

```text
VN_Index_Scoring_Quarterly_Quant_Model/
├── .github/workflows/            # CI/CD: quarterly_scoring (đầu mỗi quý) · batch_scoring (backtest 24 quý) · validate_data (hàng ngày)
├── data/
│   ├── raw/                      # Cache dữ liệu thô (vn30_tickers.json, macro_sbv.csv)
│   ├── processed/                # Dữ liệu sạch đã căn chỉnh mốc thời gian
│   └── features/                 # Ma trận đặc trưng 4 nhóm biến số
├── output/
│   ├── exports/                  # score_*.json + 2 Excel workbook (8 sheet & 20 sheet siêu chi tiết)
│   ├── reports/                  # Báo cáo HTML (index.html = dashboard 24 quý)
│   └── charts/                   # Biểu đồ phân rã điểm số và hàm phản ứng xung
├── scripts/                      # backfill_calibrated_scores · rebuild_html · generate_excel_report · export_excel_detailed · inject validators
├── src/
│   ├── data/fetcher.py           # Data Ingestion: vnstock 4.0.2 (Quote, Listing) & yfinance & VNDirect
│   ├── features/                 # macro · valuation · flow · technical · global
│   ├── models/                   # regression/mlr_model · var/var_model · ml/ml_model
│   ├── scoring/quarterly_scorer.py  # Bộ tính điểm 2 tầng: raw + Calibrated Action Signal
│   └── reporting/                # report_builder (HTML 2 tầng + dashboard) · excel_builder
├── tests/                        # 113 tests: calibration, label sync, point-in-time, ADTV, flows backfill, export...
├── run_quarterly.py              # Entrypoint chạy pipeline theo quý
└── run_daily_update.py           # Entrypoint cập nhật tín hiệu hàng ngày sau giờ đóng cửa
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

#### Cách 4b: Xuất Excel SIÊU CHI TIẾT toàn bộ dữ liệu (`scripts/export_excel_detailed.py`)
```bash
python scripts/export_excel_detailed.py
# -> output/exports/VN_Index_Detailed_Data_Export.xlsx (20 sheet, ~2.200 dòng)
#    01_Summary / 02-03_Pillars: điểm 24 quý (RAW + calibrated + weighted)
#    04_Factor_Details: MỖI factor MỖI quý — text gốc + score parse được
#    05_Market_Inputs / 06_Flows_Audit / 07_ADTV: input thật từng quý
#      (trái phiếu NS, M2 ADB/GSO, P/E-P/B-EYG z; flows z mới vs cũ)
#    08_MLR / 09_Granger / 10-12_ML: regression + causality + walk-forward
#      từng fold + feature importance từng quý
#    13_Rationale / 14_Index_Prices / 15-16_Nguồn ngoài
#    17_NA_Register: sổ đăng ký N/A — mục nào fill bằng nguồn nào,
#      mục nào còn N/A cố ý (pe_zscore 2021 — giới hạn dữ liệu thật)
# Test: tests/test_excel_detailed_export.py (13 test — đủ 24 quý, khớp
# parquet lịch sử, flows z 24/24, N/A register trung thực)
```

#### Cách 5: Chạy Cập nhật Tín hiệu Hàng ngày (`run_daily_update.py`)
Dùng sau 16:05 UTC+7 (giờ Việt Nam) mỗi ngày giao dịch để kiểm tra diễn biến giá, dòng tiền khối ngoại và cảnh báo biến động bất thường:
```bash
python run_daily_update.py
```

---

## 🤖 TỰ ĐỘNG HÓA CI/CD (GITHUB ACTIONS)

Dự án tích hợp sẵn 4 workflows tự động trong `.github/workflows/`:
1. **`quarterly_scoring.yml`**:
   - Tự động kích hoạt vào lúc 09:00 UTC+7 (giờ Việt Nam) ngày đầu tiên của mỗi quý (ngày 1 các tháng 1, 4, 7, 10).
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
