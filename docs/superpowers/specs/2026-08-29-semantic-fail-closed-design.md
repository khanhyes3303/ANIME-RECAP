# Semantic Fail-Closed Design

## Mục tiêu

Không cho Antigravity hoàn thành một tập chỉ bằng cách làm JSON hợp lệ, cân tổng thời
lượng audio/video hoặc tự điền critic sạch. Engine phải chặn đúng các lỗi đã quan sát
trong BLACK TORCH tập 001 trước khi render/publish thành phẩm.

## Bằng chứng thất bại hiện tại

- 47/47 beat có action window đúng 1.000 ms trong khi mỗi TTS dài khoảng 8–10 giây.
- 20/47 beat trỏ frame evidence nằm ngoài shot của source range được dựng.
- Beat 34 lấy source từ 874.957 ms dù hành động/lời tương ứng chỉ bắt đầu gần
  883.360 ms, làm voice đi trước hình và giữ cả title card BLACK TORCH.
- Script tạm chọn `source_start + TTS duration`, không chọn footage theo hành động.
- Critic script/video được sinh hàng loạt với `finding_codes=[]` và cùng một note;
  proxy không được phản biện thật.
- Audit 33 ms chỉ đo tổng duration, không đo semantic sync; `repair_history` và
  `stage_metrics` trống nhưng run vẫn đạt `HOAN_THANH`.

## Invariant mới

1. `frame_evidence` của beat phải là shot frame thuộc chính source range của beat.
2. ACTION/REACTION phải bắt đầu hành động không muộn hơn 750 ms từ lúc voice của beat
   bắt đầu và action window phải phủ ít nhất 35% TTS dự kiến, tối thiểu 1.500 ms.
3. Source range không được được suy ra chỉ bằng `start + TTS duration`; EDL chấp nhận
   nhiều range liên tục theo ý nghĩa nhưng từng range phải mang shot/event thật.
4. Sau storyboard, engine tự trích ba SOURCE anchor cho mỗi range. Sau proxy/final,
   engine tự trích ba PROGRAM anchor cho mỗi segment.
5. Critic SCRIPT phải dẫn đủ SOURCE anchor. Critic VIDEO phải dẫn đủ SOURCE và
   PROGRAM anchor, ghi quan sát hình riêng từng beat và verdict sync có cấu trúc.
6. Cùng một critic note/visual observation không được lặp hàng loạt. ID khác nhau chỉ
   là metadata, không còn đủ để chứng minh critic độc lập.
7. Final audit tự tải anchor manifest do engine tạo, kiểm tra đủ start/middle/end và
   chỉ tính coverage cho beat có verdict MATCH, evidence đầy đủ, không finding chặn.
8. `HOAN_THANH` yêu cầu stage metrics thực tế; báo cáo trống không được publish.
9. Truth hỗ trợ các vùng loại bỏ `TITLE_CARD`, `EYECATCH`, `STUDIO_LOGO`; mọi source
   range giao vùng EXCLUDE đều bị chặn như OP/ED/credits/preview.
10. Prompt một lần chạy phải có đường dẫn job thật; không còn placeholder khiến người
    dùng tưởng có thể dán nguyên văn.

## Giới hạn trung thực

Không có validator thuần timestamp nào tự hiểu nội dung anime. Semantic verdict vẫn
cần model thị giác, nhưng engine sẽ buộc model đối chiếu đúng ảnh nguồn/ảnh program và
không thể biến một critic rỗng, lặp công thức thành PASS. Không thêm MCP, repo, OCR,
cloud API hoặc renderer mới trong thay đổi này.

