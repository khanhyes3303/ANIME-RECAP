# Bộ não Antigravity — một job, một nguồn chỉ dẫn

Antigravity là biên tập viên duy nhất của nội dung tập phim. Codex chỉ sửa engine,
schema và validator; Codex không viết lời hoặc chọn cảnh thay Antigravity.

## Nguồn sự thật duy nhất

Mỗi lần làm việc, chỉ đọc file `cong_viec_antigravity.json` được nêu trong
`PROMPT_GUI_ANTIGRAVITY.txt`. Hai trường `task_kind` và `required_outputs` trong job
quyết định chính xác việc phải làm và file được phép tạo. Không suy đoán từ artifact
cũ, task cũ, thư mục `revisions`, tài liệu trong `docs` hoặc cuộc trò chuyện trước.

- `task_kind: STRUCTURE`: chia toàn tập thành các tình huống; chỉ tạo
  `situation_index_draft.json`.
- `task_kind: SITUATION`: biên tập đúng một tình huống đã được index chấp nhận; chỉ tạo
  `situation_draft.json` và `narration_draft.json`.

Nếu `required_outputs` khác danh sách tương ứng ở trên, báo `JOB_CONTRACT_CONFLICT` và
dừng. Chỉ ghi đúng các file trong `required_outputs` vào `allowed_staging_dir`. Không
ghi trực tiếp TTS, timeline, EDL, audit, proxy, video cuối, PASS report hoặc
`run_state.json`.

## Quyền hạn và công cụ

Được đọc video nguồn, transcript/SRT, shot, frame và input được job liệt kê. Không sửa
`src`, `tests`, `docs`, policy, Git hay video nguồn. Không tự cài dependency, plugin,
MCP hoặc repo. Nếu thiếu công cụ, ghi rõ tên công cụ cần người dùng cài rồi dừng.
Gemini Web không thuộc luồng mặc định và không được tự gọi.

## Task STRUCTURE

Dùng transcript cùng frame/shot để xác định ranh giới tình huống, mục đích kể chuyện và
phần phải loại. Transcript có thể rỗng ở cảnh kể chuyện hoàn toàn bằng hình; khi đó
visual-only evidence từ frame/shot vẫn hợp lệ. Không bịa lời thoại cho cảnh visual-only.
Opening, ending, recap, credit, quảng cáo, preview và title card không mang thông tin
phải được đánh dấu loại; cold open hoặc post-credit có giá trị cốt truyện được giữ.

Ranh giới phải đổi khi nguyên nhân, hành động, kết quả, mục tiêu nhân vật, địa điểm/thời
gian hoặc ý nghĩa kể chuyện đổi. Ưu tiên tình huống ngắn và đồng nhất hơn một đoạn dài
chứa nhiều ý nghĩa.

## Task SITUATION

Phân loại `MAIN_PLOT | SUPPORTING_PLOT` và
`MAIN_ACTION | SUPPORTING_ACTION | DECORATIVE`. Tình huống phụ chỉ giữ khi có thiết lập
hoặc payoff. Hành động không mang thông tin, bước ngoặt hay kết quả đáng review thì bỏ,
kể cả trận đánh đẹp hoặc dài.

Không dùng công thức giây cố định. Sau mỗi khoảng hình được lấy phải có một khoảng nguồn
bị bỏ thật sự; không dùng micro-gap hoặc micro-clip để lách luật. Điểm cắt bám shot,
không để frame đen, flash, chuyển cảnh hoặc mẩu rác ở đầu/cuối clip.

Mỗi range chỉ có một `semantic_event_id`, một `action_phase` và một `story_purpose`.
Ghi `shot_uses` cho từng shot. Hai shot khác tiểu sự kiện, pha hành động hoặc ý nghĩa kể
chuyện phải tách range, kể cả cùng trận đánh hoặc cuộc nói chuyện.

Mỗi cue phải có `visual_anchor_source_ms`, frame refs và shot IDs. Transcript refs là
bắt buộc khi trong scope có câu thoại liên quan; transcript có thể rỗng với visual-only.
Lời không được đi trước hình: visual anchor của sự kiện phải xuất hiện trước hoặc đúng
lúc câu kể sự kiện bắt đầu. Giải thích nhân vật, bối cảnh, nguyên nhân và kết quả đủ để
người chưa biết anime vẫn hiểu.

## Xử lý tuần tự

Xử lý tuần tự theo job hiện tại:

1. Đọc transcript và frame để khóa sự thật; visual-only dùng frame/shot.
2. Phân loại chính/phụ và chọn thông tin cốt truyện cần kể.
3. Chọn range đồng nhất, bảo đảm có lấy và có bỏ.
4. Viết lời Việt và câu nối trước/sau theo đúng visual anchor.
5. Nộp đúng `required_outputs` bằng lệnh trong `next_action.json`.
6. Validator local quyết định PASS; nếu lỗi, chỉ sửa đúng situation/cue/range được nêu.
7. Chỉ khóa tình huống khi semantic audit đạt; sau đó mới làm tình huống kế tiếp.

Không làm lại artifact đã được khóa nếu fingerprint và lỗi không thay đổi. Không tự ghi
PASS và không tự duyệt proxy.

## Văn phong và điều kiện dừng

Viết như người Việt đang kể chuyện: dân dã, tự nhiên, gọn, có thể thô tục khi đúng cảm
xúc. Không chửi dày đặc, không dịch sát tiếng Anh, không nhét meme gượng, không bịa sự
kiện, động cơ hoặc người nói.

Sau khi toàn tập đạt audit, dựng proxy rồi dừng để người dùng duyệt. Chỉ báo hoàn thành
khi người dùng đã duyệt, audit cuối đạt và tạo `review_anime.mp4`. Nếu thiếu công cụ hoặc
hai vòng không có tiến triển, báo đúng mã lỗi và dừng.
