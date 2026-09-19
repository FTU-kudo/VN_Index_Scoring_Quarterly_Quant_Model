# VN-Index Quarterly Quantitative Scoring Model

**Phien ban**: 1.0.0 | **Cap nhat**: Q3/2026 | **Ngay tao**: 19/09/2026

## Mo ta

He thong Phan tich Dinh luong Toan dien cho VN-Index.
Chay theo quy (tu dong qua GitHub Actions CI/CD).

## Cau truc

- src/data/fetcher.py         - Fetch VNI, macro, global, NFF
- src/features/               - Feature engineering 6 nhom bien so
- src/models/regression/      - MLR voi Newey-West HAC
- src/models/var/             - VAR + Granger Causality + IRF
- src/models/ml/              - XGBoost + Walk-Forward Validation
- src/scoring/                - Cham diem 6 nhom x trong so
- src/reporting/              - Bao cao HTML + JSON

## Chay

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Chinh .env voi VNSTOCK_API_KEY

# Chay pipeline Q3/2026
python run_quarterly.py --quarter 2026-Q3

# Cap nhat hang ngay
python run_daily_update.py
```

## CI/CD

- quarterly_scoring.yml : Chay tu dong dau moi quy (1/1, 1/4, 1/7, 1/10)
- validate_data.yml     : Kiem tra du lieu hang ngay (T2-T6)

## Disclaimer

Nghien cuu va giao duc. Khong phai khuyen nghi dau tu chinh thuc.
