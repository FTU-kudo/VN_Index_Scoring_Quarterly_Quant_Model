"""ledger_sync.py — Đồng bộ ledger audit input với lần chấm điểm live
=====================================================================

Bối cảnh (root cause GitHub Actions runs #18/#19, 2026-Q4)
----------------------------------------------------------
`run_quarterly.py` chấm điểm bằng dữ liệu live và ghi
`output/exports/score_<Q>.json` + cache giá `vnindex_quarterly_close.json`
(report_builder tự ghi). NHƯNG ba ledger input dùng để dựng workbook công thức

    data/scores/vnindex_quarterly_market_data.json
    data/scores/vnindex_quarterly_flows.json
    data/scores/vnindex_quarterly_adtv.json

trước đây CHỈ được ghi bởi `scripts/backfill_*.py` chạy tay. Khi một quý đã
publish được chấm lại bằng dữ liệu mới (2026-Q4: snapshot 2026-09-25 →
quarter-end 2026-09-30), JSON điểm đổi còn ledger thì không → workbook dựng từ
ledger cũ lệch khỏi JSON → `verify_workbook_accuracy.py` FAIL.

Module này đóng hợp đồng đó lại: ngay sau khi chấm điểm, ledger của ĐÚNG quý
vừa chấm được ghi lại từ CHÍNH input point-in-time mà scorer đã dùng
(`score_record["pit_scorer_inputs"]`).

Nguyên tắc:
  * chỉ chạm vào entry của quý đang chấm — các quý lịch sử không đổi;
  * merge chứ không xoá: các key do backfill tạo (`rescored`, `scores`,
    `*_old`, ...) được giữ nguyên;
  * input thiếu (None) KHÔNG được thay bằng số mặc định — key được ghi None
    đúng như scorer đã thấy;
  * idempotent: chạy lại cùng một quý với cùng input → file không đổi
    (ngoại trừ dấu thời gian `updated_at` khi nội dung thực sự thay đổi).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MARKET_DATA_LEDGER = "vnindex_quarterly_market_data.json"
FLOWS_LEDGER = "vnindex_quarterly_flows.json"
ADTV_LEDGER = "vnindex_quarterly_adtv.json"


def _load(path: Path) -> Dict[str, Any]:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            raise ValueError(f"Ledger không hợp lệ (phải là object): {path}")
        payload.setdefault("quarters", {})
        return payload
    return {"description": "", "quarters": {}}


def _write_if_changed(path: Path, payload: Dict[str, Any], before: str) -> bool:
    payload["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    candidate = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False)
    # So sánh bỏ qua updated_at để giữ tính idempotent
    probe = dict(payload)
    probe.pop("updated_at", None)
    probe_before = json.loads(before) if before else {}
    probe_before.pop("updated_at", None)
    if probe_before == probe:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(candidate + "\n")
    return True


def _merge_quarter(ledger: Dict[str, Any], quarter: str, entry: Dict[str, Any]) -> None:
    quarters = ledger.setdefault("quarters", {})
    existing = quarters.get(quarter)
    merged = dict(existing) if isinstance(existing, dict) else {}
    for key, value in entry.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            sub = dict(merged[key])
            sub.update(value)
            merged[key] = sub
        else:
            merged[key] = value
    quarters[quarter] = merged


def sync_quarter_ledgers(
    quarter: str,
    pit_inputs: Dict[str, Any],
    scores_dir: Path,
    adtv_windows: Optional[Dict[str, Any]] = None,
) -> Dict[str, bool]:
    """Ghi lại ledger input của `quarter` từ input point-in-time của scorer.

    Returns
    -------
    dict {tên ledger: đã thay đổi?}
    """
    if not isinstance(pit_inputs, dict) or not pit_inputs:
        raise ValueError(
            "pit_scorer_inputs rỗng — không đồng bộ ledger từ nguồn không xác định"
        )

    scores_dir = Path(scores_dir)
    as_of = pit_inputs.get("as_of")
    bonds = dict(pit_inputs.get("bonds") or {})
    macro = dict(pit_inputs.get("macro") or {})
    valuation = dict(pit_inputs.get("valuation") or {})
    flows = dict(pit_inputs.get("flows") or {})
    structure = dict(pit_inputs.get("structure") or {})

    changed: Dict[str, bool] = {}

    # ── 1. market_data: bonds + FX + M2 + Z-score định giá ───────────────────
    md_path = scores_dir / MARKET_DATA_LEDGER
    md = _load(md_path)
    md_before = json.dumps(md, ensure_ascii=False, indent=1)
    md_entry: Dict[str, Any] = {
        "quarter": quarter,
        "as_of": as_of,
        "bonds": {
            "vn1y_yield": bonds.get("vn1y_yield"),
            "delta_vn1y_yield": bonds.get("delta_vn1y_yield"),
            "vn10y_yield": bonds.get("vn10y_yield"),
            "vn_yield_spread": bonds.get("vn_yield_spread"),
            "bond_date": as_of,
        },
        "fx_zscore": macro.get("fx_zscore"),
        "pepb_z": {
            "pe": valuation.get("pe_zscore"),
            "pb": valuation.get("pb_zscore"),
            "eyg": valuation.get("eyg_zscore"),
        },
        "source": "run_quarterly live scoring (pit_scorer_inputs)",
    }
    if macro.get("m2_yoy_pct") is not None:
        md_entry["m2"] = {"m2_yoy_pct": macro.get("m2_yoy_pct")}
    _merge_quarter(md, quarter, md_entry)
    changed[MARKET_DATA_LEDGER] = _write_if_changed(md_path, md, md_before)

    # ── 2. flows: z-score + %MC của NFF ex-ETF và ETF ────────────────────────
    fl_path = scores_dir / FLOWS_LEDGER
    fl = _load(fl_path)
    fl_before = json.dumps(fl, ensure_ascii=False, indent=1)
    _merge_quarter(fl, quarter, {
        "quarter": quarter,
        "as_of": as_of,
        "flows_row_date": as_of,
        "nff_z": flows.get("nff_z"),
        "nff_ytd_pct": flows.get("nff_ytd_pct"),
        "etf_z": flows.get("etf_z"),
        "etf_ytd_pct": flows.get("etf_ytd_pct"),
        "source": "run_quarterly live scoring (pit_scorer_inputs)",
    })
    changed[FLOWS_LEDGER] = _write_if_changed(fl_path, fl, fl_before)

    # ── 3. ADTV: %QoQ + cửa sổ Q−1 / Q−2 ─────────────────────────────────────
    ad_path = scores_dir / ADTV_LEDGER
    ad = _load(ad_path)
    ad_before = json.dumps(ad, ensure_ascii=False, indent=1)
    adtv_entry: Dict[str, Any] = {
        "quarter": quarter,
        "adtv_change_pct": structure.get("adtv_change_pct"),
        "source": "run_quarterly live scoring (pit_scorer_inputs)",
    }
    if adtv_windows:
        adtv_entry["windows"] = adtv_windows
    _merge_quarter(ad, quarter, adtv_entry)
    changed[ADTV_LEDGER] = _write_if_changed(ad_path, ad, ad_before)

    logger.info(
        "[LEDGER] Đồng bộ input audit cho %s (as_of=%s): %s",
        quarter, as_of,
        ", ".join(f"{name}{'=updated' if did else '=unchanged'}" for name, did in changed.items()),
    )
    return changed
