# Prompt một lần chạy Antigravity

Xử lý duy nhất tập anime trong job:

```text
<ĐƯỜNG_DẪN_RUN>\cong_viec_antigravity.json
```

Đọc toàn bộ `Bo_nao_Antigravity/GEMINI.md` và job. Chỉ xử lý task/situation hiện tại;
ghi `situation_draft.json` cùng `narration_draft.json` vào đúng `allowed_staging_dir`.
Nộp qua lệnh `accept-antigravity` trong `next_action.json`; engine sẽ tạo TTS, timeline
và quyết định PASS.

Ưu tiên thông tin và diễn biến cốt truyện. Không giữ hành động chỉ vì đẹp. Không dùng
nhịp giây cố định; mọi khoảng được lấy phải có khoảng nguồn bị bỏ thật sự sau nó.
Viết lời Việt dân dã, tự nhiên và thô tục vừa ngữ cảnh, không bịa sự kiện.

Mỗi range phải đồng nhất `semantic_event_id`, `action_phase`, `story_purpose` ở mọi shot;
tách range nếu ý nghĩa shot thay đổi. Mỗi cue phải có `visual_anchor_source_ms` và đủ
transcript/frame/shot evidence để người chưa biết anime vẫn hiểu.

Chỉ thực hiện lệnh được ghi trong `next_action.json`. Không tự sửa mã, test, policy,
`run_state.json`, video nguồn hoặc tự cài công cụ. Validator local quyết định PASS.
