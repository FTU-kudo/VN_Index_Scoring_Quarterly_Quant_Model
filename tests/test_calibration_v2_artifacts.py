"""
test_calibration_v2_artifacts.py — Hợp đồng artifact production sau calibration v2
==================================================================================
Kiểm các artifact ĐÃ COMMIT cuả production (read-only — KHÔNG ghi):

  1. score_*.json: raw score & calibrated score lưu RIÊNG, đủ field v2,
     metadata provenance (git_commit, config_hash, model_hash, data_as_of,
     generated_at, status FINAL/PROVISIONAL, calibration_method).
  2. Không quý production nào có calibrated_score chạm rail 0/100
     (bất biến thiết kế v2 — bệnh 2022-Q2=0.00 không tái phát).
  3. Idempotent rebuild: tính lại tuần tự từ parquet raw ⇒ khớp đúng giá trị
     calibrated đã lưu (cả parquet lẫn JSON) — lịch sử không drift, không trộn
     artifact cũ/mới.
  4. Status: 2026-Q4 = PROVISIONAL (nguồn data 2026-09-25 chưa tới cuối quý);
     các quý đã hoàn tất = FINAL; quy tắc tổng quát cho quý tương lai (2027-Q1+).
  5. Web ↔ JSON: diagnostics v2 (σ floored / z winsorised) xuất hiện đúng
     trên HTML của các quý bị floor; action panel nói rõ "không phải dự báo".
  6. Forward-return validation: IC(Spearman) của calibrated vs STRICT quarter
     forward return tính độc lập từ data files, khớp logic workbook; signal t
     được đánh giá trên OUTCOME tương lai (close t), không dùng outcome làm input.
"""

import json
import math
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config import SCORE_CALIBRATION
from src.utils.dates import resolve_publication_status
from src.scoring.calibration_rebuild import calibrate_history_sequentially

EXPORTS = PROJECT_ROOT / "output" / "exports"
REPORTS = PROJECT_ROOT / "output" / "reports"
PARQUET = PROJECT_ROOT / "data" / "scores" / "quarterly_scores_history.parquet"
CLOSES = PROJECT_ROOT / "data" / "scores" / "vnindex_quarterly_close.json"


def _load_json_scores():
    records = {}
    for p in sorted(EXPORTS.glob("score_*.json")):
        payload = json.loads(p.read_text(encoding="utf-8"))
        rec = payload["quarterly_score"]
        records[rec["quarter"]] = payload
    return records


def _spearman(x, y):
    xr = pd.Series(x).rank().values
    yr = pd.Series(y).rank().values
    return float(np.corrcoef(xr, yr)[0, 1])


# ═══════════════════════════════════════════════════════════════════════════
# 1–3. JSON + parquet contract
# ═══════════════════════════════════════════════════════════════════════════

class TestArtifactContract:

    def test_raw_and_calibrated_stored_separately_with_v2_fields(self):
        records = _load_json_scores()
        assert len(records) >= 24
        for q, payload in records.items():
            rec = payload["quarterly_score"]
            assert "total_score" in rec and "calibrated_score" in rec, q
            assert rec["total_score"] != rec["calibrated_score"] or \
                not rec["calibration_applied"], q  # tầng riêng — chỉ bằng nhau khi fallback
            for f in ("calibration_z", "calibration_z_raw", "calibration_hist_mean",
                      "calibration_hist_std", "calibration_std_effective",
                      "calibration_std_floored", "calibration_n_history",
                      "calibration_method", "calibration_applied"):
                assert f in rec, f"{q}: thiếu {f}"
            assert rec["calibration_method"] == SCORE_CALIBRATION["method"], q

    def test_metadata_provenance_complete(self):
        records = _load_json_scores()
        for q, payload in records.items():
            meta = payload["metadata"]
            for f in ("git_commit", "config_hash", "model_hash", "data_as_of",
                      "generated_at", "status", "calibration_method", "model_version",
                      "point_in_time"):
                assert f in meta and meta[f] not in (None, ""), f"{q}: provenance thiếu {f}"
            assert meta["status"] in ("FINAL", "PROVISIONAL"), q
            assert meta["calibration_method"] == SCORE_CALIBRATION["method"], q

    def test_no_quarter_at_rail_zero_or_hundred(self):
        """Bất biến v2: không artifact nào có calibrated = 0.00 hoặc 100.00."""
        records = _load_json_scores()
        for q, payload in records.items():
            cal = payload["quarterly_score"]["calibrated_score"]
            assert 0.0 < cal < 100.0, f"{q}: calibrated chạm rail ({cal})"

    def test_2022_q2_artifact_is_bounded_not_pinned(self):
        records = _load_json_scores()
        rec = records["2022-Q2"]["quarterly_score"]
        assert rec["total_score"] == pytest.approx(51.25, abs=0.01)
        assert rec["calibrated_score"] == pytest.approx(26.25, abs=0.10)
        assert rec["calibrated_score"] != 0.0
        assert rec["calibration_std_floored"] is True
        assert rec["calibration_hist_std"] == pytest.approx(2.874, abs=0.005)

    def test_idempotent_sequential_rebuild_from_parquet(self):
        """Rebuild tuần tự từ total_score của parquet ⇒ đúng giá trị đã commit
        (parquet & mọi JSON) — đảm bảo không trộn artifact cũ/mới sau rebuild."""
        df = pd.read_parquet(PARQUET)
        assert "2099-Q1" not in set(df["quarter"])  # hygiene: không row test
        rebuilt = calibrate_history_sequentially(
            [{"quarter": q, "total_score": s} for q, s in zip(df["quarter"], df["total_score"])]
        )
        by_q = {r["quarter"]: r for r in rebuilt}
        pq = df.set_index("quarter")
        records = _load_json_scores()
        assert set(by_q) == set(records), "parquet/JSON lệch tập quý — artifact không đồng bộ"
        for q, r in by_q.items():
            assert float(pq.loc[q, "calibrated_score"]) == pytest.approx(r["calibrated_score"], abs=0.01), q
            assert float(records[q]["quarterly_score"]["calibrated_score"]) == pytest.approx(r["calibrated_score"], abs=0.01), q
            assert float(pq.loc[q, "total_score"]) == pytest.approx(
                float(records[q]["quarterly_score"]["total_score"]), abs=0.05), q


# ═══════════════════════════════════════════════════════════════════════════
# 4. Publication status (FINAL/PROVISIONAL) — quy tắc tổng quát
# ═══════════════════════════════════════════════════════════════════════════

class TestPublicationStatus:

    def test_unit_rule(self):
        # 2026-Q4: nguồn chưa tới 2026-09-30 → PROVISIONAL
        assert resolve_publication_status("2026-Q4", "2026-09-25") == "PROVISIONAL"
        # Khi dữ liệu đã tới cuối quý → FINAL (snapshot đầu quý)
        assert resolve_publication_status("2026-Q4", "2026-09-30") == "FINAL"
        # Ngày cuối quý rơi cuối tuần/lễ ≤ tolerance vẫn coi FINAL
        assert resolve_publication_status("2024-Q1", "2023-12-29") == "FINAL"
        assert resolve_publication_status("2021-Q1", "2020-12-31") == "FINAL"
        # Thiếu data_as_of → PROVISIONAL (không bịa final)
        assert resolve_publication_status("2026-Q4", None) == "PROVISIONAL"
        # Quý tương lai 2027+ cũng dùng chung quy tắc (không hardcode mốc)
        assert resolve_publication_status("2027-Q1", "2026-12-31") == "FINAL"
        assert resolve_publication_status("2027-Q1", "2026-12-20") == "PROVISIONAL"

    def test_production_status_matches_rule(self):
        records = _load_json_scores()
        for q, payload in records.items():
            rec = payload["quarterly_score"]
            expect = resolve_publication_status(q, rec.get("data_as_of"))
            assert payload["metadata"]["status"] == expect, q
        # 2026-Q4 tại thởi điểm review: provisional vì nguồn 2026-09-25 < cuối quý
        assert records["2026-Q4"]["metadata"]["status"] == "PROVISIONAL"
        assert records["2026-Q4"]["quarterly_score"]["data_as_of"] == "2026-09-25"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Web ↔ JSON: diagnostics v2 + semantics trên HTML
# ═══════════════════════════════════════════════════════════════════════════

class TestWebConsistencyV2:

    def test_floored_quarters_show_sigma_floor_in_html(self):
        for q, qdir in (("2022-Q1", "2022_Q1"), ("2022-Q2", "2022_Q2"), ("2022-Q4", "2022_Q4")):
            html = (REPORTS / qdir / "index.html").read_text(encoding="utf-8")
            assert "floored" in html or "đặt sàn" in html, f"{q}: HTML thiếu ghi chú σ floor"

    def test_2022_q2_html_shows_bounded_score_not_zero(self):
        html = (REPORTS / "2022_Q2" / "index.html").read_text(encoding="utf-8")
        m = re.search(r'class="score-big"[^>]*>([\d.]+)</div>', html)
        assert m is not None
        assert float(m.group(1)) == pytest.approx(26.25, abs=0.1)
        assert "0.00" not in m.group(1)

    def test_action_panel_declares_non_forecast_semantics(self):
        for qdir in ("2022_Q2", "2026_Q4"):
            html = (REPORTS / qdir / "index.html").read_text(encoding="utf-8")
            assert "NOT a quarterly return/crash forecast" in html, qdir
            assert re.search(r"winsori[sz]", html.lower()) or "nén" in html.lower(), qdir

    def test_dashboard_declares_calibration_v2_legend(self):
        html = (REPORTS / "index.html").read_text(encoding="utf-8")
        assert "winsorized z-score" in html
        assert "NOT a forecast of quarterly returns" in html


# ═══════════════════════════════════════════════════════════════════════════
# 6. Forward-return validation (strict, no look-ahead)
# ═══════════════════════════════════════════════════════════════════════════

class TestForwardReturnValidation:

    def _strict_quarter_frame(self):
        """Signal tại quý t (tính từ as-of cuối t−1) vs STRICT forward return của
        đúng quý t (close t / close t−1 − 1). Outcome KHÔNG BAO GIỜ là input scoring."""
        df = pd.read_parquet(PARQUET).sort_values("quarter").reset_index(drop=True)
        closes = json.loads(CLOSES.read_text(encoding="utf-8"))
        qs = df["quarter"].tolist()
        idx = {q: i for i, q in enumerate(qs)}
        rows = []
        for _, r in df.iterrows():
            q = r["quarter"]
            i = idx[q]
            if q not in closes:
                continue
            asof_close = 1103.87 if i == 0 else closes.get(qs[i - 1])
            outcome_close = closes.get(q)
            if asof_close and outcome_close:
                rows.append({
                    "quarter": q,
                    "raw": float(r["total_score"]),
                    "cal": float(r["calibrated_score"]),
                    "strict_fwd_ret": outcome_close / asof_close - 1.0,
                })
        return pd.DataFrame(rows)

    def test_signal_evaluated_on_future_outcome_alignment(self):
        """Alignment: as-of close của quý t PHẢI bằng outcome close của t−1
        (strict point-in-time — lệch 1 quý, không dùng close quý t làm input).
        Kiểm bằng tay cho 2021-Q2: strict fwd ret = close(2021-Q2)/close(2021-Q1) − 1
        — tức outcome QUÝ TƯƠNG LAI so với decision date, không phải quá khứ."""
        closes = json.loads(CLOSES.read_text(encoding="utf-8"))
        assert closes["2021-Q1"] is not None
        frame = self._strict_quarter_frame()
        r0 = frame[frame["quarter"] == "2021-Q2"].iloc[0]
        expect = closes["2021-Q2"] / closes["2021-Q1"] - 1.0
        assert r0["strict_fwd_ret"] == pytest.approx(expect, abs=1e-9)
        # 2021-Q1 as-of = 2020-12-31 = 1103.87 (seed HOSE — PIT contract cố định)
        r1 = frame[frame["quarter"] == "2021-Q1"].iloc[0]
        assert r1["strict_fwd_ret"] == pytest.approx(closes["2021-Q1"] / 1103.87 - 1.0, abs=1e-9)

    def test_independent_ic_reconciliation(self):
        """IC(Spearman) của calibrated score vs strict forward return:
        - tính 2 cách độc lập (rank-average của scipy-free) phải khớp nhau;
        - nằm trong [-1, 1]; sample ≥ 20 quý;
        - lưu ý: đây là KIỂM CHỨNG out-of-sample, KHÔNG phải assert alpha
          (README/workbook công bố trung thực giá trị này)."""
        frame = self._strict_quarter_frame()
        assert len(frame) >= 20
        ic_cal = _spearman(frame["cal"], frame["strict_fwd_ret"])
        ic_raw = _spearman(frame["raw"], frame["strict_fwd_ret"])
        # Cách 2: công thức rank rồi pearson bằng statistics thuần
        import statistics as st
        def rank_avg(v):
            out = []
            for x in v:
                lo = sum(1 for o in v if o < x)
                eq = sum(1 for o in v if o == x)
                out.append(lo + (eq + 1) / 2)
            return out
        def pcorr(a, b):
            ma, mb = st.mean(a), st.mean(b)
            num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
            den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
            return num / den
        ic_cal2 = pcorr(rank_avg(frame["cal"].tolist()), rank_avg(frame["strict_fwd_ret"].tolist()))
        assert ic_cal == pytest.approx(ic_cal2, abs=1e-9)
        assert -1.0 <= ic_cal <= 1.0 and -1.0 <= ic_raw <= 1.0

    def test_calibrated_score_is_not_trivially_reversed_history_rank(self):
        """Signal không chỉ "tái xếp hạng quá khứ": phải tồn tại quý mà calibrated
        khác raw rank-order — 2 tầng mang thông tin khác nhau về mặt thứ hạng."""
        frame = self._strict_quarter_frame()
        raw_rank = frame["raw"].rank()
        cal_rank = frame["cal"].rank()
        # Cùng thứ hạng hoàn toàn thì mới fail; thực tế 2 tầng khác nhau ở >=1 quý
        assert not (raw_rank.values == cal_rank.values).all()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
