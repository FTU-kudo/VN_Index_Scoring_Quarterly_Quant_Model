"""
test_point_in_time.py — Enforce nguyên tắc point-in-time buy-side
==================================================================
BẤT BIẾN THIẾT KẾ: Quyết định phân bổ được ra vào NGÀY ĐẦU QUÝ,
nên dữ liệu chấm điểm quý Q chỉ được dùng thông tin đến hết quý Q-1.

Test này sẽ FAIL ngay nếu ai đó sửa resolve_quarter_dates() để
latest_cutoff quay lại cuối quý đang chấm (look-ahead bias đã từng
tồn tại trong backfill 24 quý trước fix này).

Acceptance Criteria:
  1. Mặc định (không as_of): latest_cutoff == train_end_date
     == ngày cuối quý TRƯỚC → không một điểm dữ liệu nào của quý
     đang chấm được dùng.
  2. train_end_date luôn < q_start_date.
  3. as_of giữa quý: latest_cutoff = as_of, không vượt q_end_date,
     và bị đánh dấu point_in_time=False.
  4. as_of vô nghĩa (trước cut-off huấn luyện) → ValueError.
  5. Quarter sai định dạng → ValueError.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import pytest

from src.utils.dates import resolve_quarter_dates


class TestPointInTimeDefault:
    """Chế độ mặc định — dùng cho cả live đầu quý lẫn backfill lịch sử."""

    @pytest.mark.parametrize("quarter,expected_train_end", [
        ("2021-Q1", "2020-12-31"),
        ("2023-Q2", "2023-03-31"),
        ("2025-Q3", "2025-06-30"),
        ("2026-Q4", "2026-09-30"),
    ])
    def test_latest_cutoff_is_end_of_previous_quarter(self, quarter, expected_train_end):
        qd = resolve_quarter_dates(quarter)
        assert qd["train_end_date"] == pd.Timestamp(expected_train_end)
        # BẤT BIẾN CỐT LÕI: chỉ báo latest không được chứa dữ liệu quý đang chấm
        assert qd["latest_cutoff"] == qd["train_end_date"], (
            f"{quarter}: latest_cutoff={qd['latest_cutoff'].date()} khác "
            f"train_end_date={qd['train_end_date'].date()} — look-ahead bias! "
            "Backfill phải dùng đúng tập thông tin có tại ĐẦU quý."
        )
        assert qd["point_in_time"] is True

    def test_no_data_from_scored_quarter_leaks(self):
        """latest_cutoff phải nằm TRƯỚC ngày đầu quý với mọi quý 2021-2026."""
        for year in range(2021, 2027):
            for q in range(1, 5):
                qd = resolve_quarter_dates(f"{year}-Q{q}")
                assert qd["latest_cutoff"] < qd["q_start_date"], (
                    f"{year}-Q{q}: latest_cutoff >= q_start_date — leakage!"
                )
                assert qd["train_end_date"] < qd["q_start_date"]

    def test_quarter_boundaries_correct(self):
        qd = resolve_quarter_dates("2026-Q3")
        assert qd["q_start_date"] == pd.Timestamp("2026-07-01")
        assert qd["q_end_date"] == pd.Timestamp("2026-09-30")


class TestAsOfMidQuarter:
    """Chế độ --as-of: giám sát giữa quý, không dùng cho backtest."""

    def test_as_of_mid_quarter_sets_cutoff(self):
        qd = resolve_quarter_dates("2026-Q3", as_of="2026-08-15")
        assert qd["latest_cutoff"] == pd.Timestamp("2026-08-15")
        assert qd["point_in_time"] is False, (
            "Chạy as-of giữa quý phải bị đánh dấu point_in_time=False "
            "để không lẫn vào backtest."
        )

    def test_as_of_never_exceeds_quarter_end(self):
        qd = resolve_quarter_dates("2023-Q2", as_of="2024-01-01")
        assert qd["latest_cutoff"] == qd["q_end_date"]

    def test_as_of_equal_train_end_is_point_in_time(self):
        qd = resolve_quarter_dates("2026-Q3", as_of="2026-06-30")
        assert qd["latest_cutoff"] == qd["train_end_date"]
        assert qd["point_in_time"] is True

    def test_as_of_before_train_end_raises(self):
        with pytest.raises(ValueError, match="vô nghĩa"):
            resolve_quarter_dates("2026-Q3", as_of="2026-01-15")


class TestInvalidInput:

    @pytest.mark.parametrize("bad", ["2026Q3", "2026-Q5", "2026-Q0", "abc", "2026-3"])
    def test_bad_quarter_format_raises(self, bad):
        with pytest.raises(ValueError):
            resolve_quarter_dates(bad)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
