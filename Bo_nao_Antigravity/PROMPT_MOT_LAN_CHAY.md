# Prompt một lần chạy Antigravity

Xử lý duy nhất tập anime trong job:

```text
<ĐƯỜNG_DẪN_RUN>\cong_viec_antigravity.json
```

Đọc toàn bộ `Bo_nao_Antigravity/GEMINI.md`, transcript, shot và frame của run. Tạo
`situations.json` rồi `narration_plan.json`; xử lý tuần tự và khóa xong từng tình huống
trước khi sang tình huống tiếp theo.

Ưu tiên thông tin và diễn biến cốt truyện. Không giữ hành động chỉ vì đẹp. Không dùng
nhịp giây cố định; mọi khoảng được lấy phải có khoảng nguồn bị bỏ thật sự sau nó.
Viết lời Việt dân dã, tự nhiên và thô tục vừa ngữ cảnh, không bịa sự kiện.

Chỉ thực hiện lệnh được ghi trong `next_action.json`. Không tự sửa mã, test, policy,
`run_state.json`, video nguồn hoặc tự cài công cụ. Validator local quyết định PASS.
