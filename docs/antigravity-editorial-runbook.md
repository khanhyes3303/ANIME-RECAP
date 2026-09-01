# Runbook review anime toàn tập

Luồng mặc định dùng một task cấu trúc và một task biên tập toàn tập. Không có vòng xử lý
từng tình huống.

## Trình tự

1. `prepare --run RUN_DIR` trích transcript, shots và frames.
2. Antigravity hoàn thành task `STRUCTURE`; engine nhận và khóa `situation_index.json`.
3. `editor-task --run RUN_DIR` tạo một task `EPISODE_REVIEW` với
   `situation_id="__episode__"`.
4. Antigravity xem evidence toàn tập và ghi đúng `situations_draft.json` cùng
   `narration_draft.json`.
5. `accept-antigravity` kiểm đủ mọi tình huống editable, thứ tự, phạm vi, grounding và
   ngân sách từ; hai bản nháp được publish cùng một manifest hash.
6. Engine kiểm định nội dung toàn cục, tạo TTS cho mọi cue và đo tổng voice thật.
7. Voice ngoài 420.000–720.000 ms trả toàn bộ tập về một revision biên tập mới. Cue
   không đổi dùng lại cache.
8. Engine dựng một semantic timeline, audit mạch toàn tập, render và audit proxy.
9. Dừng tại `CHO_NGUOI_DUNG_DUYET_PROXY`. Người dùng duyệt hoặc từ chối proxy.

## Quyền sở hữu

- Antigravity: hiểu cảnh, chọn/bỏ đoạn, viết lời và visual anchor.
- Engine: schema, provenance, duration, cache, timeline, render và machine audit.
- Người dùng: đánh giá cuối cùng lời kể có đúng cảnh/tình huống và duyệt proxy.

Proxy có thể dùng độ phân giải/bitrate thấp hơn video cuối để dựng nhanh, nhưng vẫn phải
giữ đúng timeline, voice, cảnh và audit.

## Resume

Sau mất mạng, chạy lại `operator --run RUN_DIR`. Task ID và input hash đang hoạt động
được dùng lại. Không task mới nào được tạo khi task cũ chưa accept hoặc chưa bị route
về revision sửa lỗi.

## Chuyển run cũ

```powershell
uv run python run_episode.py migrate-run --run "RUN_DIR" --reason whole-episode-review
```

Lệnh giữ source reference, transcript/SRT, shots, frames và accepted situation index.
Narration, TTS, timeline, audits, task/status và proxy cũ được chuyển vào
`revisions/whole-episode-review-revision-N`; sau đó run bắt đầu lại từ một
`EPISODE_REVIEW` sạch. Archive có thể phục hồi, không bị xóa.
