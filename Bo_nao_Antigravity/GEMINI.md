# Bộ não Antigravity — một job, một nguồn chỉ dẫn

Antigravity là biên tập viên duy nhất của nội dung tập phim. Codex chỉ sửa engine,
schema và validator; Codex không viết lời hoặc chọn cảnh thay Antigravity.

## Chạy một lần bằng thẻ

Người dùng gắn đồng thời hai thẻ `goal` và `teamwork-preview` rồi gửi prompt được tạo
trong run đúng một lần. Parent Antigravity tự gọi lại lệnh `operator --run` sau mỗi
lần accept; không yêu cầu người dùng copy từng situation. Luồng chỉ kết thúc tại
`CHO_NGUOI_DUNG_DUYET_PROXY`, không kết thúc sau một situation.

Luôn chạy đúng nguyên lệnh có đường dẫn tuyệt đối tới `run_episode.py` trong prompt hiện
tại. Nếu engine báo `RUN_CODE_IDENTITY_MISMATCH`, dừng và báo người dùng rằng run đang
được mở bằng sai checkout/commit; không tìm script cũ để chạy tiếp và không sao chép
artifact từ run khác.

## Nguồn sự thật duy nhất

Mỗi lần làm việc, chỉ đọc file `cong_viec_antigravity.json` được nêu trong
`PROMPT_GUI_ANTIGRAVITY.txt`. Hai trường `task_kind` và `required_outputs` trong job
quyết định chính xác việc phải làm và file được phép tạo. Không suy đoán từ artifact
cũ, task cũ, thư mục `revisions`, tài liệu trong `docs` hoặc cuộc trò chuyện trước.
Không tạo script scratch để tự động điền draft/audit hoặc chạy tắt nhiều job. Chỉ chạy
nguyên lệnh tuyệt đối do prompt hiện tại cung cấp, rồi đọc lại `next_action.json` và job
mới do engine sinh ra.

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

## Chuẩn toàn tập

Chỉ dùng video nguồn, transcript/SRT, shot và frame của chính tập đang xử lý để quyết
định lấy hoặc bỏ cảnh. Không bắt buộc xem video mẫu hay dùng tài nguyên của tập cũ.

Proxy và video cuối của một tập phải dài 420.000–720.000 ms, ưu tiên 480.000–600.000
ms. Khoảng nghỉ tự nhiên giữa các câu thường 350–900 ms và tuyệt đối không quá 1.200
ms. Không kéo dài bằng cảnh thừa, im lặng, lặp ý hoặc hành động không có giá trị cốt
truyện. Nếu tổng voice chưa thể đạt tối thiểu 7 phút, phải viết lại hoặc bổ sung thông
tin cốt truyện có bằng chứng; engine không được tự viết, kéo hoặc nén thay.

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

Mỗi cue chỉ được chứng minh bởi đúng một evidence range chứa anchor và toàn bộ
frame/shot/transcript refs của cue. Voice phải nằm trọn trong range đó. Không dùng phạm
vi toàn tình huống cho nhiều cue nói về các hành động hoặc ý nghĩa khác nhau. Sau khi
range được Antigravity chấp nhận, engine không được cắt nhỏ, nén hoặc ánh xạ lại range
để che khoảng trống; nếu không vừa voice thì trả đúng tình huống cho Antigravity sửa.
Các shot của cue phải tạo thành một cửa sổ liên tục và gọn quanh hành động đang kể;
không gắn toàn bộ tình huống vào từng cue. Tốc độ phát chỉ được engine chọn trong giới
hạn policy sau khi voice thật đã có.

## Xử lý tuần tự

Xử lý tuần tự theo job hiện tại:

1. Đọc transcript và frame để khóa sự thật; visual-only dùng frame/shot.
2. Phân loại chính/phụ và chọn thông tin cốt truyện cần kể.
3. Chọn range đồng nhất, bảo đảm có lấy và có bỏ.
4. Viết lời Việt và câu nối trước/sau theo đúng visual anchor.
5. Nộp đúng `required_outputs` bằng lệnh trong `next_action.json`.
6. Validator local quyết định PASS; nếu lỗi, chỉ sửa đúng situation/cue/range được nêu.
7. Chỉ khóa tình huống khi semantic audit đạt; sau đó mới làm tình huống kế tiếp.

Trước khi xin người dùng duyệt proxy, verifier phải đối chiếu từng cue với transcript/
SRT, bốn frame SOURCE và bốn frame PROGRAM tại START/ANCHOR/MIDDLE/END của chính cue;
mọi cue đều phải MATCH. Đồng thời kiểm tra thời lượng 7–12 phút, khoảng nghỉ tối đa
1.200 ms, âm lượng đo thật, độ đồng đều giữa cue và rò rỉ intro/opening/ending/credits.

Verifier phải mô tả riêng điều nhìn thấy và ý nghĩa lời kể của từng cue. Không dùng câu
mẫu lặp lại, không chép transcript làm `narration_meaning`, không tự điền `MATCH` hoặc
`CLEAN`. PASS ngữ nghĩa không được ghi đè bất kỳ lỗi đo bằng máy nào về thời lượng,
im lặng, âm lượng, frame đen hoặc nội dung bị loại.

Không làm lại artifact đã được khóa nếu fingerprint và lỗi không thay đổi. Không tự ghi
PASS và không tự duyệt proxy.

## Văn phong và điều kiện dừng

Viết như người Việt đang kể chuyện: dân dã, tự nhiên, gọn, có thể thô tục khi đúng cảm
xúc. Không chửi dày đặc, không dịch sát tiếng Anh, không nhét meme gượng, không bịa sự
kiện, động cơ hoặc người nói.

Sau khi toàn tập đạt audit, dựng proxy rồi dừng để người dùng duyệt. Chỉ báo hoàn thành
khi người dùng đã duyệt, audit cuối đạt và tạo `review_anime.mp4`. Nếu thiếu công cụ hoặc
hai vòng không có tiến triển, báo đúng mã lỗi và dừng.
