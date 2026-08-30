# Runbook biên tập anime theo tình huống

Luồng mặc định là local và không cần Gemini Web. Antigravity là bên duy nhất viết nội
dung tập phim; Codex chỉ duy trì engine, schema và validator.

## Nguyên tắc không được phá

- Task đầu tiên chỉ chia cấu trúc toàn tập và chỉ ghi `situation_index_draft.json`.
- Sau khi engine khóa chỉ mục, mỗi task nội dung chỉ nhận transcript, shots và frames
  nằm trong một situation; task chỉ ghi `situation_draft.json` cùng
  `narration_draft.json` vào staging được cấp. Không tham chiếu manifest toàn tập.
- Mỗi range chỉ có một tiểu sự kiện, một pha hành động và một mục đích kể chuyện. Tách
  ngay khi các shot đổi ý nghĩa; ưu tiên 4 giây đồng nhất hơn 10 giây lộn xộn.
- Mỗi cue phải có transcript, frame, shot và `visual_anchor_source_ms`. Lời chỉ phát sau
  khi hình mốc đã xuất hiện với preroll quy định.
- Người mới chưa biết anime phải hiểu được nhân vật, thuật ngữ, nguyên nhân, bước ngoặt
  và kết quả theo đúng thứ tự.
- Không tự cài dependency, plugin, MCP hay repo. Nếu thiếu, dừng và báo chính xác tên
  công cụ để người dùng cài.
- Codex không được sửa lời kể hay tự chọn cảnh. Gemini Web chỉ là chẩn đoán tùy chọn cho
  run legacy, không được tạo PASS cho luồng này.

## Vòng đời một tập

1. `prepare --run RUN_DIR` trích transcript, shot và frame, tạo task chia cấu trúc.
2. Antigravity đọc `cong_viec_antigravity.json`, chia ranh giới theo ý nghĩa và viết
   đúng `situation_index_draft.json` vào staging.
3. `accept-situation-index --run RUN_DIR --task TASK_ID --input STAGING_DIR` kiểm source
   hash, range, thứ tự và bằng chứng rồi khóa `situation_index.json`.
4. `editor-task --run RUN_DIR` vật lý hóa input chỉ thuộc situation kế tiếp trong index.
   Antigravity đọc packet thu hẹp và viết đúng hai draft nội dung vào staging.
5. `accept-antigravity --run RUN_DIR --task TASK_ID --input STAGING_DIR` khóa hash đầu
   vào, lưu provenance và đưa draft vào kiểm định.
6. `audit --run RUN_DIR --phase situation` kiểm schema, sự thật, range và mạch nhân quả.
7. `tts --run RUN_DIR --situation SITUATION_ID` tạo audio riêng cho từng cue.
8. `timeline --run RUN_DIR --situation SITUATION_ID` đặt cue sau visual anchor, dựng audio
   đã căn thời gian và chặn `VOICE_PRECEDES_VISUAL_ANCHOR`.
9. Chạy lại `audit --phase situation`. Nếu đạt, khóa situation; nếu lỗi, chỉ situation đó
   quay về Antigravity. Sau hai lần cùng fingerprint không tiến triển, dừng cho người xử lý.
10. Lặp bước 4–9 cho situation kế tiếp. Sau situation cuối, `audit --phase episode` kiểm
   người mới có hiểu được toàn tập và phát hiện bridge/fact lặp.
11. `render --quality proxy`, rồi `audit --phase proxy`.
12. Hệ thống dừng ở `CHO_NGUOI_DUNG_DUYET_PROXY`. Người dùng xem proxy và chọn:
    `approve-proxy --run RUN_DIR`, hoặc
    `reject-proxy --run RUN_DIR --note "mô tả lỗi" --situation situation-XXX`.
13. Chỉ sau khi approval hash hợp lệ mới chạy `render --quality final` và
    `audit --phase engine`. Engine kiểm lại cùng hash trước khi xuất bản.

Proxy bị từ chối không bị xóa. Revision cũ được giữ nguyên; chỉ situation bị nêu và các
artifact hạ nguồn của nó được làm lại. Với run cũ đã hoàn thành nhưng người dùng chê,
chạy `migrate-run --run RUN_DIR --reason user-rejected`; revision 1 được sao lưu trước khi
revision 2 bắt đầu.

Run v2 cũ đã chờ task nội dung nhưng chưa có index phải chạy
`migrate-run --run RUN_DIR --reason require-situation-index`. Task cũ được giữ và đánh
dấu superseded; hệ thống quay về task chia cấu trúc, không dùng lại gói toàn tập sai phạm vi.
