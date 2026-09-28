# data/external — Dữ liệu nguồn committed (không phải dữ liệu sinh ra bởi pipeline)

## hose_market_cap_published.csv

Vốn hóa niêm yết HOSE (tỷ VND) tại các mốc **đã công bố** — dùng làm mẫu số
thật cho `nff_pct = net foreign flow / market cap` trong giai đoạn mà
`ticker_history.parquet` (dataset PE/PB) **chưa có số cổ phiếu đầy đủ**
(trước ~2021-04-15 dataset chỉ có 26–142 mã → total_mc ~10 nghìn tỷ, sai lệch
~300 lần so với thực tế ~3–4 triệu tỷ).

### Cách dùng (tự động trong `build_foreign_flow_features`)

- Daily MC = **nội suy tuyến tính theo thời gian** giữa các mốc công bố.
- Từ **2021-04-15** (ngày đầu tiên ticker_history có MC đầy đủ ≥ 1 triệu tỷ,
  376 mã): dùng total_mc thật của ticker_history — điểm splice 2021-04-15
  (4.784.377 tỷ) được thêm làm mốc cuối của chuỗi nội suy.
- Với mọi ngày có flows mà MC ticker **NaN hoặc < 1.000.000 tỷ** (ngưỡng sanity
  — HOSE thực tế 2018+ luôn ≥ 2,8 triệu tỷ): thay bằng MC công bố nội suy.

### Nguồn từng mốc

| Ngày | MC (tỷ VND) | Nguồn |
|---|---|---|
| 2018-08-31 | 3.157.672 | Suy từ số HOSE công bố: 31/08/2019 = 3,32 triệu tỷ, +5,13% YoY (Nhân Dân 18/09/2019) → 3.320.000/1,0513 |
| 2018-12-31 | 2.875.721 | Suy từ số HOSE công bố: 31/12/2019 = 3,28 triệu tỷ, +14,05% YoY (VNEconomy 07/01/2020, báo cáo tổng kết 2019 của HOSE) → 3.280.000/1,1405 |
| 2019-08-31 | 3.320.000 | HOSE qua Nhân Dân 18/09/2019 |
| 2019-09-30 | 3.370.000 | HOSE qua Thị trường Tài chính Tiền tệ 20/12/2019 |
| 2019-11-30 | 3.300.000 | HOSE qua Thị trường Tài chính Tiền tệ 20/12/2019 |
| 2019-12-31 | 3.280.000 | Báo cáo tổng kết 2019 của HOSE (VNEconomy 07/01/2020) |
| 2020-12-31 | 4.080.000 | HOSE (VietnamPlus 06/01/2021) |

**Chéo-kiểm chứng 2018:** hai nguồn độc lập (YoY của báo cáo tổng kết 2019:
2.875.721 tỷ; YoY tại 30/11/2019 của Thị trường Tài chính Tiền tệ:
3.300.000/1,151 = 2.867.072 tỷ) lệch nhau 0,3% — nhất quán.

### Giới hạn đã ghi rõ (không che giấu)

- MC 2018–2020 là **nội suy giữa các mốc công bố** (độ lệch thực tế có thể
  ±5% trong năm) — dùng làm **mẫu số** của tỉ lệ nff/etf, không phải số liệu
  giao dịch. Tử số (flows) 100% là dữ liệu giao dịch thật từ VNDirect.
- Từ 2021-04-15 mẫu số là MC thật tính từ ticker_history — không nội suy.
