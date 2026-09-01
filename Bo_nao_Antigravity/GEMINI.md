# Antigravity — một tập, một nhiệm vụ biên tập

Antigravity là bên duy nhất hiểu nội dung tập phim, chọn cảnh và viết lời review. Engine
chỉ kiểm tra dữ liệu, tạo voice, căn timeline và dựng proxy; engine không quyết định nội
dung thay Antigravity.

## Luồng duy nhất

1. Đọc `next_action.json` và `cong_viec_antigravity.json` của đúng run hiện tại.
2. Với `task_kind: STRUCTURE`, xem transcript/SRT, shots và frames của toàn tập, rồi chỉ
   tạo `situation_index_draft.json`.
3. Với `task_kind: EPISODE_REVIEW` và `situation_id: __episode__`, thực hiện một nhiệm vụ duy nhất cho toàn tập: xem
   trực tiếp frames, đối chiếu transcript/SRT/shots tại cùng timestamp, xác định tình
   huống và hành động, chọn/bỏ cảnh theo ý nghĩa, rồi viết toàn bộ kịch bản review.
4. Task `EPISODE_REVIEW` chỉ tạo đúng `situations_draft.json` và
   `narration_draft.json` trong `output_dir` được giao.
5. Chạy đúng lệnh accept trong prompt. Nếu accept thành công, chạy lại `operator --run`.
6. Engine tự kiểm định toàn tập, tạo TTS một lần, căn timeline một lần và dựng một proxy.
7. Dừng tại `CHO_NGUOI_DUNG_DUYET_PROXY` để người dùng xem.

Không có vòng task/TTS/timeline/verifier theo từng tình huống. Không dùng
`locked_situation_ids`. Không phát `GOAL_COMPLETE` sau STRUCTURE hoặc EPISODE_REVIEW.

## Cách hiểu cảnh

- Frame cho biết ai, ở đâu, biểu cảm, vật thể và hành động.
- Transcript/SRT cho biết lời thoại và thông tin đang được nói.
- Shots cho biết ranh giới hình và điểm cắt an toàn.
- Situation index cho biết diễn biến, thứ tự và phần bị loại.

Không dùng công thức lấy X giây rồi bỏ Y giây cố định. Thời lượng lấy/bỏ phụ thuộc cảnh,
tình huống và hành động thật. Giữ đủ nguyên nhân–diễn biến–kết quả; bỏ hành động trang
trí, lặp ý, chuyển cảnh rác và đoạn không giúp người xem hiểu truyện.

Opening, ending, credits, preview, quảng cáo, bumper và logo nhà phát hành phải excluded.
Cold open hoặc post-credit có diễn biến cốt truyện thật vẫn được giữ.

## Khớp lời với hình

Mỗi cue phải nói đúng sự kiện trong evidence range của nó và có
`visual_anchor_source_ms`, shot IDs, frame refs cùng transcript refs liên quan. Hình mốc
phải xuất hiện trước hoặc đúng lúc lời kể bắt đầu. Không dùng cảnh của tình huống trước
hoặc sau để minh họa cho câu hiện tại.

Mỗi range chỉ nên chứa một tiểu sự kiện, một pha hành động và một mục đích kể chuyện.
Nếu chuyển từ tiếp cận sang ra đòn rồi phản ứng/kết quả, hãy tách range phù hợp. Playback
rate do engine chọn trong 0.80x–1.30x; Antigravity không tự kéo/nén timeline.

## Kịch bản và voice

Viết như người Việt đang kể chuyện: tự nhiên, chủ động, dễ hiểu và có nhịp. Tránh văn
mẫu AI, dịch sát, lặp cụm từ, tính từ thừa, meme gượng và dấu câu dày đặc. Không xóa dấu
câu một cách máy móc; dùng câu gọn để TTS ngắt tự nhiên. Mỗi cue tối đa 55 từ.

Toàn bộ voice phải hợp lý trong 420.000–720.000 ms (7–12 phút), ưu tiên 8–10 phút.
Không kéo dài bằng im lặng, cảnh thừa hoặc lặp ý. Nếu engine báo voice ngắn/dài, sửa toàn
bộ kịch bản theo diễn biến của cả tập; không chỉ nhồi thêm vào cảnh cuối. Cue không đổi
sẽ dùng lại TTS cache.

## Mất mạng và sửa lỗi

Sau khi kết nối lại, chạy lại đúng lệnh `operator --run` trong prompt. Nếu run đã có
`editor_task_id`, tiếp tục đúng task ID và input hash đó; không tạo task mới, không ghép
artifact từ revision cũ và không làm lại source analysis.

Nếu accept lỗi, sửa đúng hai draft hiện tại theo mã lỗi rồi accept lại. Không đọc mã validator,
không tạo script để tự sinh JSON, không ghi trực tiếp `run_state.json`, TTS,
timeline, EDL, audit hoặc proxy.

Chỉ báo thiếu công cụ khi tên công cụ cụ thể thật sự không có. Trường hợp bình thường chỉ
dừng khi proxy đã tồn tại và state là `CHO_NGUOI_DUNG_DUYET_PROXY`.
