# Thiết kế sửa luồng review anime thực tế

## Mục tiêu

Giữ nguyên quy trình nghiệp vụ hiện tại: Antigravity đọc frame, transcript và SRT;
chọn đoạn nguồn; viết lời review; engine tạo TTS, khớp từng câu với cảnh, ghép video
7–12 phút và dừng cho người dùng duyệt. Thay đổi này chỉ loại bỏ các đường tắt khiến
code thực tế không làm đúng quy trình đó.

Trong lúc phát triển và kiểm thử không gọi Antigravity, không tạo TTS thật và không
render lại toàn bộ tập. Test dùng fixture và runner giả để không tiêu quota.

## 1. Chỉ chạy code thuộc repository của run

Mọi lệnh tiếp tục một run phải kiểm tra repository identity đã lưu trong run: đường dẫn
repository chuẩn và Git commit tạo run. Nếu lệnh được gọi từ checkout khác hoặc code cũ
hơn contract của run, lệnh dừng với `RUN_CODE_IDENTITY_MISMATCH` trước khi thay đổi state.

Prompt và lệnh tự động phải dùng `run_episode.py` tuyệt đối từ repository chuẩn; không
được dựa vào current working directory của script ngoài. Không sao chép draft từ
`revisions` hoặc run cũ để thay cho việc thực hiện job hiện tại.

## 2. Khớp từng cue với đúng evidence range

Mỗi cue chỉ dùng đúng evidence range chứa visual anchor của cue. Thời lượng chương
trình của range được tính từ voice của cue cộng preroll, postroll và khoảng nghỉ tự
nhiên. Engine được chọn tốc độ hình trong policy và cắt ở ranh giới shot đã được
Antigravity đánh dấu; không giữ toàn bộ tình huống và không dùng một tốc độ chung để
che khoảng trống.

Nếu evidence đã chọn dài hơn mức tốc độ tối đa có thể khớp voice, hoặc ngắn hơn mức
tốc độ tối thiểu, engine không tự bịa/cắt tùy tiện. Nó trả lỗi có `situation_id`,
`cue_id`, thời lượng voice, thời lượng evidence và khoảng cần sửa để Antigravity chỉ
sửa đúng cue đó.

Trước khi render, timeline phải thỏa tất cả điều kiện:

- Tổng thời lượng từ 420.000 đến 720.000 ms, ưu tiên 480.000–600.000 ms.
- Voice không đi trước visual anchor.
- Khoảng im lặng đầu, giữa và cuối không quá 1.200 ms.
- Mỗi cue nằm trọn trong range hình tương ứng.

Nếu tổng voice dưới mức đủ tạo video 7 phút liên tục, engine trả về Antigravity để bổ
sung lời có bằng chứng. Engine không kéo dài video bằng im lặng hoặc cảnh thừa.

## 3. Không chấp nhận verifier giả

Xóa đường chạy có thể tự điền `MATCH`/`CLEAN` mà không đọc bằng chứng. Audit máy chạy
trước verifier và kiểm tra dữ liệu đo thật: duration, stream, A/V drift, khoảng im lặng,
loudness và giới hạn timeline. Bất kỳ lỗi máy nào cũng chặn trạng thái
`CHO_NGUOI_DUNG_DUYET_PROXY`.

Verifier ngữ nghĩa phải nộp nhận xét dựa trên cue text, transcript/SRT, source frames và
program frames. Validator từ chối nhận xét mẫu, nhận xét trùng lặp không mô tả nội dung
quan sát, narration meaning lấy nguyên transcript thay vì lời review, hoặc toàn bộ kết
quả `MATCH` không có bằng chứng riêng cho từng cue.

Verifier chỉ đánh giá ngữ nghĩa. Nó không thể ghi đè lỗi duration, silence, loudness,
stream hoặc drift do audit máy phát hiện.

## 4. Luồng mặc định sau khi sửa

Luồng người dùng thấy chỉ còn các mốc:

1. `PHAN_TICH`: Antigravity đọc nguồn và chọn tình huống/cảnh.
2. `VIET_REVIEW`: Antigravity viết lời Việt gắn với từng cue/range.
3. `TAO_VOICE_VA_KHOP_CANH`: engine tạo TTS và tính timeline từng cue.
4. `DUNG_VIDEO`: engine ghép các đoạn ngắn thành proxy.
5. `KIEM_TRA`: audit máy rồi kiểm tra ngữ nghĩa thực.
6. `CHO_NGUOI_DUNG_DUYET_PROXY`.

Ledger và revision có thể tồn tại bên trong để khôi phục lỗi, nhưng không tạo thêm bước
người dùng và không được coi là bằng chứng video đúng. Các CLI cũ vẫn được giữ trong
giai đoạn chuyển đổi nếu test còn phụ thuộc, nhưng không nằm trên đường chạy mặc định.

## 5. Kiểm thử và tiêu chí hoàn thành

Thêm test hồi quy chứng minh:

- Lệnh chạy từ checkout sai bị chặn trước khi đổi state.
- Fixture có 277 giây voice và 764 giây evidence không thể được duyệt hoặc render thành
  proxy đạt.
- Timeline co/cắt từng cue trong policy, không để gap lớn hơn 1.200 ms.
- Timeline ngoài 7–12 phút bị chặn trước render.
- Proxy audit gán cứng `MATCH/CLEAN` bị từ chối.
- Lỗi audit máy không thể bị verifier ngữ nghĩa ghi đè.
- Luồng hợp lệ vẫn đi đến `CHO_NGUOI_DUNG_DUYET_PROXY`.

Hoàn thành khi toàn bộ unit/integration test liên quan vượt qua, test suite hiện có
không hồi quy, và một dry-run bằng fixture đi hết luồng mà không gọi dịch vụ
Antigravity/TTS thật.
