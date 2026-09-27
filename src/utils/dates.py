"""
dates.py — Point-in-time date resolution cho pipeline chấm điểm quý
=====================================================================
NGUYÊN TẮC BUY-SIDE (bất biến):
  Quyết định phân bổ tài sản được đưa ra vào NGÀY GIAO DỊCH ĐẦU TIÊN
  của quý. Do đó, MỌI dữ liệu dùng để chấm điểm quý Q chỉ được phép
  là thông tin đã tồn tại TRƯỚC thời điểm đó — tức đến hết phiên
  giao dịch cuối cùng của quý (Q-1).

  Nguyên tắc này áp dụng cho CẢ HAI chế độ:
    - Live   : chạy cron đầu quý (thông tin tự nhiên dừng ở cuối quý trước)
    - Backfill: chạy lại quý lịch sử (PHẢI cắt dữ liệu y hệt như live,
                nếu không backtest sẽ bị look-ahead bias)

Cung cấp một hàm duy nhất: resolve_quarter_dates()
"""

from typing import Optional, Dict

import pandas as pd


def resolve_quarter_dates(quarter: str, as_of: Optional[str] = None) -> Dict:
    """
    Tính các mốc cut-off dữ liệu cho một quý chấm điểm.

    Parameters
    ----------
    quarter : str
        Định dạng "YYYY-QN", ví dụ "2026-Q3".
    as_of : str, optional
        Ngày "hiện tại" giả định (YYYY-MM-DD) cho lần chạy giám sát GIỮA quý.
        - None (mặc định) → point-in-time chuẩn tại ĐẦU QUÝ:
          latest_cutoff = ngày cuối quý trước (không look-ahead).
          Đây là chế độ BẮT BUỘC cho backfill/backtest.
        - Có giá trị → latest_cutoff = min(as_of, ngày cuối quý).
          KHÔNG dùng cho backtest lịch sử.

    Returns
    -------
    dict với các khóa:
        q_start_date   : pd.Timestamp — ngày đầu tiên của quý
        q_end_date     : pd.Timestamp — ngày cuối cùng của quý
        train_end_date : pd.Timestamp — cut-off huấn luyện mô hình
                         (= ngày cuối quý trước, không leakage)
        latest_cutoff  : pd.Timestamp — cut-off cho chỉ báo "latest"
                         dùng để chấm điểm (xem as_of ở trên)
        point_in_time  : bool — True nếu latest_cutoff đúng chuẩn đầu quý

    Raises
    ------
    ValueError nếu quarter sai định dạng hoặc as_of nằm trước cut-off
    huấn luyện (vô nghĩa).
    """
    try:
        y_str, q_str = quarter.split("-Q")
        year, q = int(y_str), int(q_str)
    except Exception as exc:
        raise ValueError(
            f"Quarter '{quarter}' sai định dạng — cần 'YYYY-QN' (ví dụ 2026-Q3)"
        ) from exc
    if not 1 <= q <= 4:
        raise ValueError(f"Quarter '{quarter}': N phải trong [1, 4], nhận {q}")

    m_start = (q - 1) * 3 + 1
    q_start_date = pd.Timestamp(year=year, month=m_start, day=1)
    # Cut-off huấn luyện = ngày cuối quý TRƯỚC (không leakage)
    train_end_date = q_start_date - pd.Timedelta(days=1)
    # Ngày cuối quý hiện tại
    q_end_date = pd.Timestamp(year=year, month=q * 3, day=1) + pd.offsets.MonthEnd(1)

    if as_of is None:
        # Point-in-time chuẩn: thông tin có tại ĐẦU quý = đến hết quý trước
        latest_cutoff = train_end_date
        point_in_time = True
    else:
        as_of_ts = pd.to_datetime(as_of)
        if as_of_ts < train_end_date:
            raise ValueError(
                f"as_of={as_of_ts.date()} nằm trước cut-off huấn luyện "
                f"{train_end_date.date()} của {quarter} — vô nghĩa. "
                f"Dùng quý sớm hơn hoặc bỏ --as-of."
            )
        # Không bao giờ vượt quá ngày cuối quý đang chấm
        latest_cutoff = min(as_of_ts, q_end_date)
        point_in_time = latest_cutoff <= train_end_date

    return {
        "q_start_date":   q_start_date,
        "q_end_date":     q_end_date,
        "train_end_date": train_end_date,
        "latest_cutoff":  latest_cutoff,
        "point_in_time":  point_in_time,
    }
