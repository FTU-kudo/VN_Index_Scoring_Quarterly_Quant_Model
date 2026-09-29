"""
config.py — Cấu hình trung tâm cho VN_Index_Scoring_Quarterly_Quant_Model
==========================================================================
MỌI path, threshold, và tham số đều được định nghĩa tại đây.
Không được hardcode path ở bất kỳ file nào khác.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# ── Đường dẫn gốc ────────────────────────────────────────────────────────────
ROOT_DIR   = Path(__file__).resolve().parents[2]   # project root
DATA_DIR   = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"
LOGS_DIR   = ROOT_DIR / "logs"

RAW_DIR       = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
FEATURES_DIR  = DATA_DIR / "features"
SCORES_DIR    = DATA_DIR / "scores"

REPORTS_DIR = OUTPUT_DIR / "reports"
CHARTS_DIR  = OUTPUT_DIR / "charts"
EXPORTS_DIR = OUTPUT_DIR / "exports"

# Tạo các thư mục cần thiết nếu chưa tồn tại
for _d in [RAW_DIR, PROCESSED_DIR, FEATURES_DIR, SCORES_DIR,
           REPORTS_DIR, CHARTS_DIR, EXPORTS_DIR, LOGS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

# ── API Credentials (từ .env, không bao giờ hardcode) ─────────────────────────
load_dotenv(ROOT_DIR / ".env")
VNSTOCK_API_KEY = os.getenv("VNSTOCK_API_KEY", "")

# ── Khoảng thời gian dữ liệu ─────────────────────────────────────────────────
# Dữ liệu lịch sử tối đa cho backtest & calibration
HISTORY_START   = "2018-01-01"   # 8+ năm dữ liệu
HISTORY_END     = datetime.now().strftime("%Y-%m-%d")   # Ngày hiện tại (Dynamic)

# Cửa sổ Z-score (năm)
ZSCORE_WINDOW_YEARS = 5          # Rolling 5 năm cho P/E, P/B Z-score
# Số phiên tối thiểu để tính Z-score (fix 09/2026: trước đây window//2 = 2.5 năm
# khiến P/E, P/B, EYG Z-score N/A ở 2021→2023-Q2 dù dữ liệu PE/PB có từ 2019-08
# — series ex-Vingroup chỉ bắt đầu ~2021-03 do thiếu shares trước đó).
# 252 phiên = 1 năm: giá trị Z cho các ngày ≥2.5 năm dữ liệu GIỮ NGUYÊN
# (min_periods chỉ mở khoá NaN sớm hơn, không đổi mean/std của window).
ZSCORE_MIN_PERIODS_DAYS = 252

# ── Tham số VN-Index & VN30 (Dynamic Fetching) ──────────────────────────────
VNINDEX_TICKER  = "VNINDEX"


def get_vn30_tickers(source: str = "VCI", force_refresh: bool = False) -> list:
    """
    Lấy danh sách mã cổ phiếu rổ VN30 ĐỘNG từ nguồn vnstock API, không hardcode.
    Tự động cache vào data/raw/vn30_tickers.json và fallback an toàn khi offline.

    Parameters
    ----------
    source : str
        Nguồn dữ liệu vnstock (mặc định 'VCI')
    force_refresh : bool
        Nếu True, bỏ qua cache và truy vấn trực tiếp từ API

    Returns
    -------
    list[str]
        Danh sách các mã cổ phiếu VN30 hiện hành (30 mã)
    """
    cache_file = RAW_DIR / "vn30_tickers.json"

    # 1. Trả về từ cache nếu có và không ép refresh
    if not force_refresh and cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                tickers = data.get("tickers", [])
                if len(tickers) >= 30:
                    return tickers
        except Exception:
            pass

    # 2. Lấy động từ vnstock API
    try:
        from vnstock.api.listing import Listing
        l = Listing()
        res = l.symbols_by_group("VN30")
        if hasattr(res, "tolist"):
            raw_list = res.tolist()
        elif hasattr(res, "symbol"):
            raw_list = res["symbol"].tolist()
        elif isinstance(res, (list, tuple)):
            raw_list = list(res)
        else:
            raw_list = [str(x) for x in res]

        tickers = sorted([str(t).strip().upper() for t in raw_list if t and str(t).strip()])
        if len(tickers) >= 30:
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump({
                        "updated_at": datetime.now().isoformat(),
                        "source": f"vnstock.api.listing (source={source})",
                        "count": len(tickers),
                        "tickers": tickers
                    }, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
            return tickers
    except Exception as e:
        logging.getLogger(__name__).warning(f"[CONFIG] Không thể lấy VN30 trực tiếp từ vnstock: {e}")

    # 3. Fallback đọc từ cache cũ nếu có
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                cached = data.get("tickers", [])
                if cached:
                    return cached
        except Exception:
            pass

    # 4. Fallback an toàn (snapshot thực tế từ HOSE tháng 09/2026)
    return [
        "ACB", "BID", "BSR", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", "LPB",
        "MBB", "MCH", "MSN", "MWG", "SAB", "SHB", "SSB", "SSI", "STB", "TCB",
        "TCX", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VPL", "VRE"
    ]


# Biến VN30_TICKERS được tải động từ vnstock API (không hardcode)
VN30_TICKERS = get_vn30_tickers()

# ── Tham số mô hình MLR ───────────────────────────────────────────────────────
MLR_LAG_PERIODS = [1, 2, 3, 4]   # Lag 1-4 tuần cho biến độc lập
MLR_TRAIN_RATIO = 0.75            # 75% train / 25% test
# Horizon dự báo forward của MLR (phiên giao dịch, ~1 tháng).
# Target = TRUNG BÌNH log-return/ngày của {h} phiên KẾ TIẾP (t+1..t+h) —
# không phải return cùng ngày (nowcast). Giữ scale per-day để tương thích
# với hệ số quy đổi điểm trong quarterly_scorer (MLR: 50 + pred*20000,
# VAR: 50 + pred*5000 — xem SCORE_CALIBRATION và score_quant_model).
MLR_FORECAST_HORIZON_DAYS = 21

# Model scoring parameters: single source of truth for scorer and audit artifacts.
SCORE_MODEL_PARAMS = {
    "quant_model": {"mlr_gain": 20000.0, "var_gain": 5000.0},
    "ml_signal": {"neutral_score": 50.0, "max_directional_distance": 30.0,
                   "neutral_confidence": 1.0 / 3.0},
}
# 2.1.0: calibration v2 — σ-floor + z-winsorize + distance-from-raw guardrail
# (method tag: winsorized_expanding_zscore_v2, xem SCORE_CALIBRATION bên dưới).
MODEL_VERSION = "2.1.0-calibration-v2"

# Required fields only. Informational rows (bonuses, counts and contextual ratios)
# are deliberately excluded from coverage denominators.
REQUIRED_SCORING_FIELDS = {
    "macro_monetary": ("vn1y_yield", "ir_trend", "usd_vnd", "m2_yoy_growth", "vn_bonds"),
    "global_intermarket": ("dxy", "us10y", "nff_ex_etf", "jpy_carry", "oil_shock"),
    "valuation_leverage": ("pe_zscore", "pb_zscore", "margin_risk", "eyg_zscore"),
    "quant_model": ("mlr_forecast", "var_forecast", "mlr_adj_r2", "granger_leaders"),
    "ml_forecast": ("model_quality", "ml_signal"),
    "market_structure": ("ftse_upgrade", "rebalancing", "adtv", "etf_flow"),
}

# ── Tham số mô hình VAR ───────────────────────────────────────────────────────
VAR_MAX_LAGS    = 8               # AIC/BIC lựa chọn lag tối ưu trong [1, 8]
VAR_VARIABLES   = [
    "vni_return",         # Biến phụ thuộc: tỷ suất sinh lợi VNI
    "delta_vn1y_yield",   # Δ Lợi suất TPCP 1Y (proxy OMO)
    "delta_dxy",          # Δ Chỉ số DXY
    "delta_usdjpy",       # Δ Tỷ giá USD/JPY (Yen Carry Trade)
    "net_foreign_flow",   # Dòng tiền khối ngoại (tỷ VND)
    "delta_us10y",        # Δ Lợi suất TPCP Mỹ 10Y
    "pe_zscore",          # Z-score P/E VN-Index so 5Y history
    "delta_margin_debt",  # Δ Dư nợ margin toàn thị trường (%)
]

# ── Tham số ML ───────────────────────────────────────────────────────────────
ML_LOOKBACK_DAYS   = 20    # Rolling window đặc trưng (ngày giao dịch)
ML_FORECAST_DAYS   = 5     # Dự báo T+5 (1 tuần)
ML_TARGET_THRESHOLD = 0.005  # Ngưỡng ±0.5% để phân loại UP/DOWN/NEUTRAL
ML_N_SPLITS_WFV    = 8     # Số fold Walk-Forward Validation

# Hyperparameters cho mô hình ML
ML_XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "eval_metric": "mlogloss",
    "verbosity": 0
}

ML_LGBM_PARAMS = {
    "n_estimators": 200,
    "max_depth": 4,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
    "verbose": -1
}

# ── Tham số chấm điểm theo quý ───────────────────────────────────────────────
SCORING_WEIGHTS = {
    "macro_monetary":   0.25,
    "global_intermarket": 0.20,
    "valuation_leverage": 0.20,
    "quant_model":        0.15,
    "ml_forecast":        0.10,
    "market_structure":   0.10,
}
assert abs(sum(SCORING_WEIGHTS.values()) - 1.0) < 1e-9, "Tổng trọng số phải = 1.0"

# Thang điểm phân loại tổng hợp
# NGUỒN SỰ THẬT DUY NHẤT (Single Source of Truth) cho phân loại điểm.
# CẢNH BÁO: Chỉ sửa ở đây — report_builder.py PHẢI đọc từ dict này,
# KHÔNG được hardcode lại ngưỡng ở bất kỳ nơi nào khác.
# Test tự động `test_score_label_sync` sẽ FAIL nếu có sai lệch.
SCORE_LABELS = {
    (80, 100): ("BUY",        "🟢", "Highly favorable environment — Increase exposure aggressively",       "85–100% Equities"),
    (65,  79): ("ACCUMULATE", "🔵", "Gradually accumulate — Controllable risks",                         "70–85% Equities"),
    (50,  64): ("HOLD",       "🟡", "Neutral — Await confirming signals",                                "40–60% Equities"),
    (35,  49): ("REDUCE",     "🟠", "Reduce exposure — Increasing pressure",                             "20–40% Equities"),
    ( 0,  34): ("SELL",       "🔴", "Defensive — Unfavorable environment",                               "0–20% Equities"),
}

# Tuple đã sắp xếp để get_score_label() duyệt từ cao xuống thấp
SCORE_LABEL_RANGES = tuple(sorted(SCORE_LABELS.items(), key=lambda x: x[0][0], reverse=True))

# ── Calibrated Action Signal (Tầng 2 — tín hiệu hành động) ─────────────────────
# VẤN ĐỀ GỐC: điểm thô (raw composite) bị nén quanh 45-61 → 22/24 quý dính nhãn
# HOLD → z-score expanding được thêm (PR trước) để tạo phân tán regime.
# VẤN ĐỀ PHÁT SINH (postmortem 2026-09, quý 2022-Q2 thành 0.00):
#   Cửa sổ đầu lịch sử (n=4..7 quý) có σ ước lượng rất nhỏ (2.7–2.9 điểm) vì các
#   điểm thô 2021 nén chặt → z bị thổi phồng (51.25 vs μ=62.6, σ=2.87 → z=−3.95)
#   → calibrated = clip(50 + 15z, 0, 100) ghim thẳng về 0. Một raw ~trung lập
#   không thể thành tín hiệu cực đoan chỉ vì σ mẫu nhỏ.
# GIẢI PHÁP V2 (winsorized + guardrail hybrid — method="winsorized_expanding_zscore_v2"):
#   σ_eff  = max(σ_hist_sample(ddof=1), min_std)      ← sàn phương sai
#   z_eff  = clip((raw − μ_hist) / σ_eff, ±z_cap)     ← winsorize z
#   pre    = center + z_scale × z_eff                 ∈ [5, 95] với tham số mặc định
#   cal    = clip( min(max(pre, raw − max_dist), raw + max_dist), clip_low, clip_high )
# Tính chất bảo đảm: (1) raw ~50 không bao giờ tự động thành 0; (2) 0/100 không
# thể xảy ra với tham số mặc định (bão hoà 5/95 ở |z|=3σ); (3) đơn điệu theo raw
# với cùng lịch sử; (4) expanding CHỈ các quý TRƯỚC — không look-ahead; (5) tín
# hiệu low-confidence (σ yếu/mẫu nhỏ) không thể cực đoan; (6) mọi tham số nằm ở
# đây — single source of truth, workbook Excel 01_Model_Config phản chiếu cùng giá trị.
SCORE_CALIBRATION = {
    "enabled":      True,    # tắt để quay về hành vi chỉ dùng raw composite
    "method":       "winsorized_expanding_zscore_v2",  # version tag (provenance)
    "center":       50.0,    # điểm calibrated trung tâm
    "z_scale":      15.0,    # 1σ lịch sử (sau sàn) ≈ ±15 điểm calibrated
    "min_history":  4,       # cần ≥ 4 quý TRƯỚC đó mới hiệu chỉnh
    "min_std":      5.0,     # SÀN σ_hist: tin cậy tối thiểu ~5đ (dispersion dài hạn
                             #   của composite toàn mẫu ≈ 6đ; σ ước lượng < 5đ là
                             #   artefact cửa sổ nhỏ, không phải regime ổn định)
    "z_cap":        3.0,     # winsorize z tại ±3σ → bán kính đáp ứng ±45đ (5–95)
    "max_dist_from_raw": 25.0,  # guardrail hybrid: tín hiệu hành động không lệch
                             #   raw composite quá ±25đ (nửa thang nhãn)
    "clip_low":     0.0,
    "clip_high":    100.0,
}

# Trạng thái publication: quý được coi FINAL khi data_as_of cách ngày cuối quý
# TRƯỚC đó (lý tưởng) không quá N ngày — vừa đủ hấp thụ lệch cuối tuần/ngày lễ
# (tối đa ~3 ngày với lịch HOSE), PROVISIONAL khi nguồn chưa phủ hết cuối quý.
# Dùng chung cho run_quarterly + backfill + JSON metadata + HTML hero.
SCORE_STATUS_PROVISIONAL_TOLERANCE_DAYS = 4


def get_score_label(score: float):
    """
    Trả về (label, emoji, description, allocation) cho điểm số.

    Nguồn sự thật duy nhất — mọi nơi cần gán nhãn PHẢI gọi hàm này.

    Parameters
    ----------
    score : float — tổng điểm 0-100

    Returns
    -------
    tuple: (label_str, emoji_str, description_str, allocation_str)

    Lưu ý half-open intervals (fix 09/2026):
    SCORE_LABEL_RANGES là các dải NGUYÊN liên tiếp (0-34, 35-49, 50-64,
    65-79, 80-100) nhưng total_score/calibrated_score là số THẬP (làm tròn
    2 chữ số). Nếu dò theo `lo <= score <= hi`, điểm rơi VÀO KHOẢNG TRỐNG
    (vd 34.51, 49.74, 64.99) không khớp dải nào và rơi vào fallback HOLD
    mặc định — sai về ngữ nghĩa (49.74 rõ ràng là "chưa tới HOLD" → REDUCE).
    Fix: dải [lo, next_lo) — điểm thập phân thuộc dải MỚI CHƯA ĐẠT ngưỡng
    trên (34.51 → SELL, 49.74 → REDUCE, 64.99 → HOLD, 79.99 → ACCUMULATE).
    Điểm nguyên cho kết quả GIỐNG HỆT trước fix (34→SELL, 35→REDUCE, …).
    """
    n_bands = len(SCORE_LABEL_RANGES)
    # Sắp xếp tăng dần theo ngưỡng dưới — không phụ thuộc thứ tự khai báo
    ranges = sorted(SCORE_LABEL_RANGES, key=lambda x: x[0][0])
    for i, ((lo, hi), values) in enumerate(ranges):
        if i + 1 < n_bands:
            if lo <= score < ranges[i + 1][0][0]:
                return values
        else:  # dải cuối — inclusive tới 100
            if lo <= score <= hi:
                return values
    # Fallback (score ngoài [0, 100] do lỗi numeric)
    return ("HOLD", "🟡", "Neutral — Await confirming signals", "40–60% Equities")

# ── Ngưỡng cảnh báo margin call ───────────────────────────────────────────────
# Khi VN-Index giảm quá mức này (%), margin call rủi ro cao
MARGIN_CALL_DROP_PCT   = -0.12    # -12% → ngưỡng cảnh báo
MARGIN_CALL_SEVERE_PCT = -0.18    # -18% → ngưỡng nguy hiểm cao

# ── Ngưỡng Z-score định giá ───────────────────────────────────────────────────
PE_ZSCORE_OVERBOUGHT = +1.5    # Z > +1.5 → đắt
PE_ZSCORE_OVERSOLD   = -1.5    # Z < -1.5 → rẻ
PB_ZSCORE_OVERBOUGHT = +1.5
PB_ZSCORE_OVERSOLD   = -1.5

# ── Ước lượng dòng vốn ETF khi nâng hạng FTSE EM ────────────────────────────
# Ước tính tổng AUM các quỹ passive ETF theo dõi FTSE All-World & EM indices
# phân bổ vào VN ~ 0.08% × ~$8,000 tỷ USD ≈ $6.4 tỷ USD (kịch bản base)
FTSE_PASSIVE_INFLOW_BASE_USD  = 6_400_000_000    # $6.4 tỷ USD (base)
FTSE_PASSIVE_INFLOW_BULL_USD  = 9_000_000_000    # $9.0 tỷ USD (bull)
FTSE_PASSIVE_INFLOW_BEAR_USD  = 3_500_000_000    # $3.5 tỷ USD (bear)

# Rebalancing schedule FTSE: March, June, September, December
FTSE_REBALANCING_MONTHS = [3, 6, 9, 12]

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FILE  = LOGS_DIR / "quant_model.log"
