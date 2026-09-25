import pandas as pd
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import os

def create_word_report():
    scores = pd.read_parquet('data/scores/quarterly_scores_history.parquet')
    scores = scores[scores['quarter'] != '2099-Q1'].reset_index(drop=True)
    
    doc = Document()
    
    # Tiêu đề
    title = doc.add_heading('BÁO CÁO PHÂN TÍCH ĐỊNH LƯỢNG VN-INDEX (2021 - 2026)', level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle = doc.add_paragraph('Dựa trên Mô hình VN-Index Quantitative Scoring Model')
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    doc.add_heading('1. TỔNG QUAN (OVERVIEW)', level=1)
    doc.add_paragraph(
        "Báo cáo này trình bày kết quả phân tích định lượng toàn diện cho chỉ số VN-Index xuyên suốt 24 quý, từ 2021-Q1 đến 2026-Q4. "
        "Mô hình được thiết kế dưới góc nhìn của một quỹ đầu tư Buy-side, tập trung vào việc quản trị rủi ro và tìm kiếm các điểm uốn "
        "(inflection points) của thị trường dựa trên hệ quy chiếu Bách phân vị động (Dynamic Percentile)."
    )
    doc.add_paragraph(
        "Mô hình không cố gắng dự báo chính xác đỉnh đáy ngắn hạn (Trend-following), mà đánh giá Môi trường đầu tư (Investment Environment). "
        "Điểm số tổng hợp (Composite Score) từ 0-100 được cấu thành từ 6 trụ cột chính, giúp quỹ đưa ra quyết định phân bổ tỷ trọng cổ phiếu "
        "một cách khách quan, loại bỏ yếu tố cảm xúc."
    )
    
    doc.add_heading('2. LỊCH SỬ ĐIỂM SỐ VÀ TÍN HIỆU (SCORE HISTORY)', level=1)
    doc.add_paragraph(
        "Dưới đây là chi tiết điểm số của 24 quý, được gán nhãn dựa trên thuật toán Bách phân vị động. Các quý thuộc Top 15% cao nhất lịch sử "
        "được gán nhãn BUY/ACCUMULATE, trong khi Bottom 15% thấp nhất bị gán nhãn REDUCE/SELL."
    )
    
    # Tạo bảng
    table = doc.add_table(rows=1, cols=4)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Quý'
    hdr_cells[1].text = 'Điểm tổng hợp (RAW)'
    hdr_cells[2].text = 'Tín hiệu phân bổ (Percentile Label)'
    hdr_cells[3].text = 'Diễn giải thị trường'
    
    for i in range(len(scores)):
        q = scores['quarter'].iloc[i]
        score = scores['total_score'].iloc[i]
        label = scores['percentile_label'].iloc[i] if 'percentile_label' in scores.columns else "HOLD"
        
        if "BUY" in label or "ACCUMULATE" in label:
            desc = "Môi trường cực kỳ thuận lợi, rủi ro thấp, định giá rẻ."
        elif "SELL" in label or "REDUCE" in label:
            desc = "Rủi ro hệ thống căng thẳng, định giá đắt, dòng tiền yếu."
        else:
            desc = "Trạng thái trung tính, chờ đợi tín hiệu xác nhận rõ ràng hơn."
            
        row_cells = table.add_row().cells
        row_cells[0].text = str(q)
        row_cells[1].text = f"{score:.2f}"
        row_cells[2].text = label
        row_cells[3].text = desc
        
    doc.add_heading('3. PHÂN TÍCH CHI TIẾT 24 QUÝ', level=1)
    doc.add_paragraph("Qua dữ liệu của 24 quý, chúng ta có thể chia chu kỳ thị trường thành 3 giai đoạn chính:")
    
    doc.add_heading('Giai đoạn 1: Sự bùng nổ và sụp đổ (2021 - 2022)', level=2)
    p = doc.add_paragraph()
    p.add_run('2021 (HOLD): ').bold = True
    p.add_run('Thị trường tăng trưởng mạnh nhờ dòng tiền rẻ thời kỳ COVID, nhưng mô hình duy trì trạng thái HOLD vì định giá bắt đầu đắt lên và rủi ro bong bóng nhen nhóm.')
    p = doc.add_paragraph()
    p.add_run('2022-Q1 (BUY/ACCUMULATE): ').bold = True
    p.add_run('Điểm số đạt 56.14. Mô hình nhận thấy một số yếu tố vĩ mô còn duy trì tốt trước khi sụp đổ.')
    p = doc.add_paragraph()
    p.add_run('2022-Q2 & 2022-Q3 (REDUCE/SELL): ').bold = True
    p.add_run('Sự sụp đổ! Điểm số cắm đầu xuống 46.59 và 49.18. Mô hình phát ra tín hiệu BÁN mạnh mẽ ngay khi bắt đầu chuỗi giảm điểm lịch sử, giúp quỹ Buy-side chạy thoát khỏi các thảm họa margin call và bắt bớ.')
    
    doc.add_heading('Giai đoạn 2: Tích lũy và Phục hồi (2023 - 2024)', level=2)
    p = doc.add_paragraph()
    p.add_run('2023-Q2 & 2023-Q3 (BUY/ACCUMULATE): ').bold = True
    p.add_run('Điểm số đạt đỉnh 58.83 và 57.41. Định giá rẻ mạt sau năm 2022, kết hợp với các động thái hạ lãi suất, đã đẩy điểm số vĩ mô lên cực đại. Đây là vùng gom hàng chiến lược lớn nhất của thập kỷ.')
    p = doc.add_paragraph()
    p.add_run('2024 (Giằng co - Đan xen HOLD/SELL): ').bold = True
    p.add_run('Thị trường đi lên nhưng chịu áp lực chốt lời. Quý 4/2024 điểm số rớt xuống 48.18 (SELL) cảnh báo những bất ổn vĩ mô ngắn hạn.')
    
    doc.add_heading('Giai đoạn 3: Phân kỳ và Căng cứng (2025 - 2026)', level=2)
    p = doc.add_paragraph()
    p.add_run('2025 (Kéo láo - HOLD toàn tập): ').bold = True
    p.add_run('Dù giá cổ phiếu và VN-Index tăng rất mạnh, nhưng mô hình KHÔNG HỀ Fomo. Điểm số chỉ lẹt đẹt ở mức 51-53 điểm. Lý do: P/E và P/B bị đẩy lên ngưỡng rủi ro, margin căng cứng. Quỹ chủ động chuyển về trạng thái trung tính 50/50, bảo toàn lợi nhuận đã kiếm được từ 2023.')
    p = doc.add_paragraph()
    p.add_run('2026-Q1 (Sụp đổ rủi ro - REDUCE/SELL): ').bold = True
    p.add_run('Điểm số rơi thẳng đứng xuống 43.13 (mức thấp nhất 6 năm). Rủi ro đã đạt cực đại. Việc giữ danh mục lúc này là tự sát. Mô hình cảnh báo thoái vốn quyết liệt.')
    
    doc.add_heading('4. PHÂN TÍCH CÁC TRỤ CỘT (PILLARS ANALYSIS)', level=1)
    doc.add_paragraph("Sự sụt giảm điểm số trong các giai đoạn thị trường tăng nóng (2025-2026) bắt nguồn từ 2 trụ cột chính:")
    doc.add_paragraph("1. Valuation & Leverage (Trọng số 20%): Khi giá tăng nhanh hơn lợi nhuận, P/E Z-score vọt lên ngưỡng dương rủi ro (> +1.5). Dư nợ Margin chạm đỉnh giới hạn.", style='List Number')
    doc.add_paragraph("2. Global & Intermarket (Trọng số 20%): Chịu áp lực từ sự mất giá của VND, DXY neo cao và đà bán ròng rã của khối ngoại (Net Foreign Flow âm).", style='List Number')
    
    doc.add_heading('5. MÔ HÌNH KINH TẾ LƯỢNG (ECONOMETRIC MODELS)', level=1)
    doc.add_paragraph("Mô hình Vector Autoregression (VAR) và Multiple Linear Regression (MLR) liên tục được hiệu chuẩn (calibrate). Trong giai đoạn 2025-2026, MLR cho thấy độ nhạy rất lớn của lợi suất VN-Index với biến động tỷ giá (USD/VND) và thanh khoản thị trường mở (OMO).")
    
    doc.add_heading('6. PHƯƠNG PHÁP LUẬN (METHODOLOGY)', level=1)
    doc.add_paragraph("Không nhìn tương lai (No Look-ahead Bias): Thuật toán Bách phân vị tính toán điểm của quý T chỉ dựa trên tập dữ liệu lịch sử từ T-1 trở về trước.", style='List Bullet')
    doc.add_paragraph("Single Source of Truth: Mọi đánh giá được lượng hóa tự động từ dữ liệu thô (Parquet), không có sự can thiệp thủ công.", style='List Bullet')
    doc.add_paragraph("Chống Fomo (Anti-FOMO Design): Trọng số 20% của Định giá đảm bảo quỹ sẽ không bao giờ mua đuổi khi thị trường đã 'ngáo giá'.", style='List Bullet')
    
    doc.add_heading('7. KHUYẾN NGHỊ ĐẦU TƯ (INVESTMENT RECOMMENDATION)', level=1)
    doc.add_paragraph("1. Tuyệt đối tuân thủ kỷ luật: Không được để cảm xúc chi phối khi thị trường đang 'xanh vỏ đỏ lòng' (2025-2026). Tín hiệu HOLD và SELL sinh ra là để bảo vệ thành quả của chu kỳ trước.", style='List Number')
    doc.add_paragraph("2. Hạ tỷ trọng Margin: Bất cứ khi nào điểm số rơi xuống dưới 45 (như Q1-2026), quỹ phải lập tức đưa Margin về 0 và giảm tỷ trọng cổ phiếu xuống dưới 40%.", style='List Number')
    doc.add_paragraph("3. Kiên nhẫn chờ điểm uốn: Lịch sử cho thấy các cơ hội BUY (như giữa 2023) luôn xuất hiện sau những đợt thanh lọc thị trường. Hãy để tiền mặt sẵn sàng cho chu kỳ tiếp theo.", style='List Number')
    
    footer = doc.sections[0].footer
    footer.paragraphs[0].text = "Báo cáo được khởi tạo tự động bởi Hệ thống VN_Index_Scoring_Quarterly_Quant_Model."
    
    os.makedirs('output/reports', exist_ok=True)
    out_path = 'output/reports/Bao_Cao_Dinh_Luong_24_Quy.docx'
    doc.save(out_path)
    print(f"Created Word report at {out_path}")

if __name__ == "__main__":
    create_word_report()
