"""
conftest.py — Test hygiene: pytest KHÔNG BAO GIỜ ghi vào dữ liệu production
===========================================================================
VẤN ĐỀ (đã từng xảy ra): compute_quarterly_score() ghi thẳng row vào
data/scores/quarterly_scores_history.parquet (production). Các test gọi scorer
với quarter "2099-Q1" / "2026-Q3" đã làm bẩn file thật — sau pytest, git status
thấy data/ bị modify và row test 2099-Q1 lọt vào lịch sử.

FIX: autouse fixture redirect SCORES_DIR (tham chiếu trong quarterly_scorer)
sang thư mục tạm của từng test → mọi ghi parquet trong test đều cách ly.
Test vẫn đọc được dữ liệu thật nếu chủ động trỏ tới path gốc (read-only).
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(autouse=True)
def isolate_scores_dir(tmp_path, monkeypatch):
    """Redirect mọi ghi SCORES_DIR của scorer sang tmp_path (mỗi test 1 thư mục)."""
    import src.scoring.quarterly_scorer as scorer_module
    fake_scores_dir = tmp_path / "scores"
    fake_scores_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(scorer_module, "SCORES_DIR", fake_scores_dir)
    yield fake_scores_dir
    # monkeypatch tự rollback — không cần teardown thủ công
