# Thiết kế chỉ mục tình huống và gói biên tập thu hẹp

## Vấn đề cần sửa

Đường chạy hiện tại tạo `situation-001` ngay sau khi trích xuất bằng chứng rồi giao
toàn bộ transcript, shots và frame manifest của tập cho một task được gọi là “một
tình huống”. Tên task và lời nhắc không tạo ra ranh giới dữ liệu thật. Antigravity có
thể vô tình trộn nhiều tình huống, còn engine không có chỉ mục để biết tình huống kế
tiếp là gì.

## Quyết định kiến trúc

Thêm một bước editorial riêng trước các task biên tập nội dung:

1. Engine trích xuất transcript, shots và frame manifest toàn tập.
2. Antigravity nhận một `episode-structure` task chỉ để lập `situation_index_draft.json`.
   Task này không viết lời review, không chọn EDL và không tạo TTS.
3. Engine kiểm schema và bằng chứng của chỉ mục, rồi chấp nhận thành
   `situation_index.json` bất biến cho revision hiện tại.
4. Engine tạo một thư mục input riêng cho tình huống đang hoạt động. Transcript,
   shots và frame refs trong thư mục đó đều phải giao với ranh giới tình huống.
5. Antigravity nhận đúng gói thu hẹp này để viết `situation_draft.json` và
   `narration_draft.json`.
6. Engine kiểm lại mọi range/ref của output nằm trong ranh giới đã khóa trước khi
   chấp nhận.

Antigravity vẫn là bên duy nhất đưa ra quyết định nội dung: chia tình huống, mô tả ý
nghĩa, chọn bằng chứng và viết lời. Engine chỉ cắt dữ liệu theo ranh giới Antigravity
đã đề xuất và thực thi các ràng buộc xác định.

## Hợp đồng dữ liệu

`SituationIndexDocument` chứa:

- `editor`: luôn là `ANTIGRAVITY`;
- `schema_version`: `situation-index-v1`;
- `source_sha256`;
- danh sách `SituationIndexEntry` tăng dần theo thời gian.

Mỗi entry chứa:

- `situation_id` duy nhất theo mẫu `situation-NNN`;
- `source_start_ms`, `source_end_ms`;
- `summary`, `story_purpose` và `boundary_reason` không rỗng;
- ít nhất một `transcript_segment_index` hoặc `shot_id` làm bằng chứng;
- `frame_refs` chỉ được tham chiếu frame có timestamp nằm trong range;
- `excluded` và `exclusion_reason` để đánh dấu opening, ending, recap, credit,
  preview hoặc phần không đáng kể.

Các entry không được chồng lấn. Khoảng trống giữa entry được phép vì nội dung dư có
thể bị bỏ. Chỉ entry `excluded=false` mới tạo task biên tập.

## Quy tắc thu hẹp dữ liệu

Với entry đang hoạt động, engine tạo:

- `transcript.json`: chỉ các segment giao với `[start, end)`;
- `shots.json`: chỉ các shot giao với `[start, end)` và được clamp vào range;
- `frames.json`: chỉ frame refs có timestamp trong range;
- `scope.json`: ID, ranh giới, hash chỉ mục và hash ba input trên.

Không file nào trong gói tình huống được chứa segment, shot hoặc frame ngoài range.
Task biên tập không được tham chiếu đường dẫn manifest toàn tập. Hash task được tính
từ các file scoped để một thay đổi ranh giới luôn tạo task revision mới.

## State machine

Đường chạy v2 trở thành:

`TRICH_XUAT_BANG_CHUNG -> CHO_ANTIGRAVITY_CHIA_TINH_HUONG ->`
`KIEM_DINH_CHI_MUC_TINH_HUONG -> CHO_ANTIGRAVITY_TINH_HUONG -> ...`

Nếu chỉ mục sai schema, chồng lấn, tham chiếu bằng chứng không tồn tại hoặc không có
tình huống được giữ, engine từ chối và phát đúng lỗi cho task structure. Nó không tự
sửa nội dung và không tự tạo ranh giới thay thế.

Sau khi một situation được khóa, engine lấy entry chưa khóa tiếp theo trong chỉ mục;
không nhận `next_situation_id` do agent tự khai. Khi không còn entry, engine chuyển
sang audit mạch truyện toàn tập.

## Tương thích và migration

Run cũ đang ở `CHO_ANTIGRAVITY_TINH_HUONG` nhưng chưa có chỉ mục hợp lệ phải được đưa
về bước structure bằng lệnh migration xác định. Draft hoặc task cũ gửi toàn tập bị
đánh dấu superseded; không bị xóa. Artifacts final/proxy cũ vẫn nằm trong thư mục
revision đã sao lưu.

## Hợp nhất vào project chính

Nhánh engine mới được tích hợp vào `feature/anime-review-mvp` bằng fast-forward sau
khi bảo toàn các thay đổi chưa commit. Các thay đổi browser/Gemini hiện có trên main
được giữ như chức năng audit tùy chọn; chúng không được phép quay lại state machine
mặc định. Nếu cùng sửa `cli.py`, hợp nhất theo từng hunk và chạy cả test mới lẫn test
Gemini cũ.

## Tiêu chí nghiệm thu

- `prepare` không còn tự tạo `situation-001`.
- Task đầu tiên sau prepare là task chia cấu trúc, chỉ yêu cầu một output index.
- Không thể tạo editor task nếu chưa có chỉ mục đã được engine chấp nhận.
- Mỗi editor task chỉ chứa dữ liệu trong một range; test cố tình nhét dữ liệu ngoài
  range phải thất bại.
- Output Antigravity tham chiếu ngoài range bị từ chối trước khi merge artifact.
- Tình huống kế tiếp luôn lấy từ chỉ mục đã khóa.
- Run BLACK TORCH hiện tại được migration về structure, không gửi lại task sai.
- Test đầy đủ, lint và kiểm tra dirty worktree đều đạt; không cài dependency tự động.
