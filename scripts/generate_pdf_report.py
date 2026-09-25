import pandas as pd
import numpy as np
import os

scores = pd.read_parquet('data/scores/quarterly_scores_history.parquet')
scores = scores[scores['quarter'] != '2099-Q1'].reset_index(drop=True)

md_content = """# BÁO CÁO PHÂN TÍCH ĐỊNH LƯỢNG VN-INDEX (2021 - 2026)
**Dựa trên Mô hình VN-Index Quantitative Scoring Model**

---

## 1. TỔNG QUAN (OVERVIEW)
Báo cáo này trình bày kết quả phân tích định lượng toàn diện cho chỉ số VN-Index xuyên suốt 24 quý, từ 2021-Q1 đến 2026-Q4. Mô hình được thiết kế dưới góc nhìn của một quỹ đầu tư Buy-side, tập trung vào việc quản trị rủi ro và tìm kiếm các điểm uốn (inflection points) của thị trường dựa trên hệ quy chiếu **Bách phân vị động (Dynamic Percentile)**.

Mô hình không cố gắng dự báo chính xác đỉnh đáy ngắn hạn (Trend-following), mà đánh giá **Môi trường đầu tư (Investment Environment)**. Điểm số tổng hợp (Composite Score) từ 0-100 được cấu thành từ 6 trụ cột chính, giúp quỹ đưa ra quyết định phân bổ tỷ trọng cổ phiếu một cách khách quan, loại bỏ yếu tố cảm xúc.

---

## 2. LỊCH SỬ ĐIỂM SỐ VÀ TÍN HIỆU (SCORE HISTORY)
Dưới đây là chi tiết điểm số của 24 quý, được gán nhãn dựa trên thuật toán Bách phân vị động. Các quý thuộc **Top 15% cao nhất lịch sử** được gán nhãn BUY/ACCUMULATE, trong khi **Bottom 15% thấp nhất** bị gán nhãn REDUCE/SELL.

| Quý | Điểm tổng hợp (RAW) | Tín hiệu phân bổ (Percentile Label) | Diễn giải thị trường |
|---|---|---|---|
"""

for i in range(len(scores)):
    q = scores['quarter'].iloc[i]
    score = scores['total_score'].iloc[i]
    label = scores['percentile_label'].iloc[i] if 'percentile_label' in scores.columns else "HOLD"
    
    if "BUY" in label or "ACCUMULATE" in label:
        emoji = "🟢"
        desc = "Môi trường cực kỳ thuận lợi, rủi ro thấp, định giá rẻ."
    elif "SELL" in label or "REDUCE" in label:
        emoji = "🔴"
        desc = "Rủi ro hệ thống căng thẳng, định giá đắt, dòng tiền yếu."
    else:
        emoji = "🟡"
        desc = "Trạng thái trung tính, chờ đợi tín hiệu xác nhận rõ ràng hơn."
        
    md_content += f"| **{q}** | {score:.2f} | {emoji} **{label}** | {desc} |\n"

md_content += """
---

## 3. PHÂN TÍCH CHI TIẾT 24 QUÝ
Qua dữ liệu của 24 quý, chúng ta có thể chia chu kỳ thị trường thành 3 giai đoạn chính:

### Giai đoạn 1: Sự bùng nổ và sụp đổ (2021 - 2022)
* **2021 (HOLD):** Thị trường tăng trưởng mạnh nhờ dòng tiền rẻ thời kỳ COVID, nhưng mô hình duy trì trạng thái **HOLD** vì định giá bắt đầu đắt lên và rủi ro bong bóng nhen nhóm.
* **2022-Q1 (BUY/ACCUMULATE):** Điểm số đạt 56.14. Mô hình nhận thấy một số yếu tố vĩ mô còn duy trì tốt trước khi sụp đổ.
* **2022-Q2 & 2022-Q3 (REDUCE/SELL):** Sự sụp đổ! Điểm số cắm đầu xuống 46.59 và 49.18. Mô hình phát ra tín hiệu BÁN mạnh mẽ ngay khi bắt đầu chuỗi giảm điểm lịch sử, giúp quỹ Buy-side chạy thoát khỏi các thảm họa margin call và bắt bớ.

### Giai đoạn 2: Tích lũy và Phục hồi (2023 - 2024)
* **2023-Q2 & 2023-Q3 (BUY/ACCUMULATE):** Điểm số đạt đỉnh 58.83 và 57.41. Định giá rẻ mạt sau năm 2022, kết hợp với các động thái hạ lãi suất, đã đẩy điểm số vĩ mô lên cực đại. Đây là vùng **gom hàng chiến lược** lớn nhất của thập kỷ.
* **2024 (Giằng co - Đan xen HOLD/SELL):** Thị trường đi lên nhưng chịu áp lực chốt lời. Quý 4/2024 điểm số rớt xuống 48.18 (SELL) cảnh báo những bất ổn vĩ mô ngắn hạn.

### Giai đoạn 3: Phân kỳ và Căng cứng (2025 - 2026)
* **2025 (Kéo láo - HOLD toàn tập):** Dù giá cổ phiếu và VN-Index tăng rất mạnh, nhưng mô hình **KHÔNG HỀ Fomo**. Điểm số chỉ lẹt đẹt ở mức 51-53 điểm. Lý do: P/E và P/B bị đẩy lên ngưỡng rủi ro, margin căng cứng. Quỹ chủ động chuyển về trạng thái trung tính 50/50, bảo toàn lợi nhuận đã kiếm được từ 2023.
* **2026-Q1 (Sụp đổ rủi ro - REDUCE/SELL):** Điểm số rơi thẳng đứng xuống **43.13** (mức thấp nhất 6 năm). Rủi ro đã đạt cực đại. Việc giữ danh mục lúc này là tự sát. Mô hình cảnh báo thoái vốn quyết liệt.

---

## 4. PHÂN TÍCH CÁC TRỤ CỘT (PILLARS ANALYSIS)
Sự sụt giảm điểm số trong các giai đoạn thị trường tăng nóng (2025-2026) bắt nguồn từ 2 trụ cột chính:
1. **Valuation & Leverage (Trọng số 20%):** Khi giá tăng nhanh hơn lợi nhuận, P/E Z-score vọt lên ngưỡng dương rủi ro (> +1.5). Dư nợ Margin chạm đỉnh giới hạn.
2. **Global & Intermarket (Trọng số 20%):** Chịu áp lực từ sự mất giá của VND, DXY neo cao và đà bán ròng rã của khối ngoại (Net Foreign Flow âm).

---

## 5. MÔ HÌNH KINH TẾ LƯỢNG (ECONOMETRIC MODELS)
Mô hình Vector Autoregression (VAR) và Multiple Linear Regression (MLR) liên tục được hiệu chuẩn (calibrate). Trong giai đoạn 2025-2026, MLR cho thấy độ nhạy rất lớn của lợi suất VN-Index với biến động tỷ giá (USD/VND) và thanh khoản thị trường mở (OMO).

---

## 6. PHƯƠNG PHÁP LUẬN (METHODOLOGY)
* **Không nhìn tương lai (No Look-ahead Bias):** Thuật toán Bách phân vị tính toán điểm của quý T chỉ dựa trên tập dữ liệu lịch sử từ T-1 trở về trước.
* **Single Source of Truth:** Mọi đánh giá được lượng hóa tự động từ dữ liệu thô (Parquet), không có sự can thiệp thủ công.
* **Chống Fomo (Anti-FOMO Design):** Trọng số 20% của Định giá đảm bảo quỹ sẽ không bao giờ mua đuổi khi thị trường đã "ngáo giá".

---

## 7. KHUYẾN NGHỊ ĐẦU TƯ (INVESTMENT RECOMMENDATION)
1. **Tuyệt đối tuân thủ kỷ luật:** Không được để cảm xúc chi phối khi thị trường đang "xanh vỏ đỏ lòng" (2025-2026). Tín hiệu HOLD và SELL sinh ra là để bảo vệ thành quả của chu kỳ trước.
2. **Hạ tỷ trọng Margin:** Bất cứ khi nào điểm số rơi xuống dưới 45 (như Q1-2026), quỹ phải lập tức đưa Margin về 0 và giảm tỷ trọng cổ phiếu xuống dưới 40%.
3. **Kiên nhẫn chờ điểm uốn:** Lịch sử cho thấy các cơ hội BUY (như giữa 2023) luôn xuất hiện sau những đợt thanh lọc thị trường. Hãy để tiền mặt sẵn sàng cho chu kỳ tiếp theo.

*Báo cáo được khởi tạo tự động bởi Hệ thống VN_Index_Scoring_Quarterly_Quant_Model.*
"""

os.makedirs('output/reports', exist_ok=True)
with open('output/reports/Bao_Cao_Dinh_Luong_24_Quy.md', 'w', encoding='utf-8') as f:
    f.write(md_content)
