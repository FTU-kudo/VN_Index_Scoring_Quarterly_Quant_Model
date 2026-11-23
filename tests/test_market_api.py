# tests/test_market_api.py
from datetime import datetime, timezone

import pytest

from src.data import yuanta


def test_daily_history_dates_bounds_and_partial_session(monkeypatch):
    bars = [{"t": int(datetime(2026, 11, day, tzinfo=timezone.utc).timestamp()),
             "o": 100, "h": 105, "l": 99, "c": 103, "v": 500} for day in (20, 23, 24)]
    calls = []
    def get(path, params):
        calls.append(params)
        return {"s": "ok", "bars": bars}
    monkeypatch.setattr(yuanta, "_get_json", get)
    before_close = datetime(2026, 11, 23, 8, 0, tzinfo=timezone.utc)
    df = yuanta.daily_history("VNINDEX", "2026-11-20", "2026-11-23", now=before_close)
    assert df.date.dt.strftime("%Y-%m-%d").tolist() == ["2026-11-20"]
    assert calls[0]["to"] == int(datetime(2026, 11, 25, tzinfo=timezone.utc).timestamp())
    after_close = datetime(2026, 11, 23, 8, 15, tzinfo=timezone.utc)
    assert len(yuanta.daily_history("VNINDEX", "2026-11-20", "2026-11-23", now=after_close)) == 2


def test_history_rejects_bad_or_empty_response(monkeypatch):
    monkeypatch.setattr(yuanta, "_get_json", lambda *a: {"s": "ok", "bars": []})
    with pytest.raises(ValueError):
        yuanta.daily_history("VNINDEX", "2026-01-01", "2026-01-02")


def test_constituents_validate_response(monkeypatch):
    monkeypatch.setattr(yuanta, "_get_json", lambda *a: {"success": True, "response": [{"StockCode": f"S{i}"} for i in range(30)]})
    assert len(yuanta.vn30_constituents()) == 30
    monkeypatch.setattr(yuanta, "_get_json", lambda *a: {"success": True, "response": []})
    with pytest.raises(ValueError):
        yuanta.vn30_constituents()


def test_challenge_redirect_rejects_foreign_host(monkeypatch):
    class Response:
        status_code = 200
        headers = {"Content-Type": "text/html"}
        text = 'window.location.href="https://evil.example/?jskey=x"'
        url = yuanta.BASE + '/test'
        def raise_for_status(self): pass
    class Session:
        def get(self, *args, **kwargs): return Response()
    monkeypatch.setattr(yuanta.requests, "Session", Session)
    with pytest.raises(ValueError, match="Unsafe"):
        yuanta._get_json('/test')
