# Prompt dự phòng — job quyết định task

Xử lý duy nhất job sau:

```text
<ĐƯỜNG_DẪN_RUN>\cong_viec_antigravity.json
```

Đọc `Bo_nao_Antigravity/GEMINI.md`, sau đó đọc `task_kind`, `required_outputs`,
`allowed_staging_dir` và input paths trong job. Đây là nguồn chỉ dẫn duy nhất:

- `STRUCTURE` chỉ tạo `situation_index_draft.json`.
- `EPISODE_REVIEW` là một nhiệm vụ toàn tập, chỉ tạo `situations_draft.json` và
  `narration_draft.json`.

Transcript có thể rỗng đối với cảnh visual-only; khi đó dùng frame/shot và không bịa lời
thoại. Chỉ thực hiện lệnh trong `next_action.json`. Không tự cài công cụ, không gọi
Gemini Web, không đọc validator và không đọc artifact revision cũ để suy đoán nhiệm vụ.
Engine local quyết định dữ liệu có đủ điều kiện chạy TTS/timeline hay không.

Run hiện tại: `<run_dir>`

Gắn thẻ `goal` và `teamwork-preview`. Mục tiêu là đưa run đến
`CHO_NGUOI_DUNG_DUYET_PROXY`; không kết thúc sau STRUCTURE hoặc EPISODE_REVIEW.
Sau mỗi accept, chạy:
`<operator_command>`.
