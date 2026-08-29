# Smoke test Gemini Web operator

Smoke test chỉ dùng một run nhỏ đã có packet hợp lệ. Không dùng video BLACK TORCH
đầy đủ cho lần đầu và không dán mật khẩu/cookie vào terminal.

## Chuẩn bị

Mở PowerShell tại `D:\FINAL REVIEW ANIME` và thay `<run_dir>` bằng đường dẫn tuyệt
đối của run test. Nếu binding Ultra chưa có, chạy `gemini-web enroll` và nhập email
trên stdin theo hướng dẫn của engine; engine chỉ lưu hash và account hint đã che.

## Kiểm tra cửa sổ thật

```powershell
uv run python run_episode.py gemini-web run --run "<run_dir>" --phase script
```

Kỳ vọng:

1. Một cửa sổ Chrome mới có profile `.local\gemini_ultra_chrome` xuất hiện, không
   dùng cửa sổ Chrome thường đang mở.
   URL bắt buộc nằm dưới `https://gemini.google.com/app`; Gemini Notebook
   (`/notebook/...`) không thuộc operator và bị chặn ngay.
2. Người dùng tự đăng nhập đúng tài khoản Google AI Ultra và tự chọn `3.7 Flash` +
   `Tư duy mở rộng`.
3. `enroll` là xác nhận thủ công một lần cho profile chuyên dụng. Operator chờ
   DOM Gemini hiển thị account control, Ultra, model và mode; email trong menu
   Chrome không bị đọc hoặc sao chép. Operator không bấm đổi model/mode.
4. Operator mở nút `Nội dung tải lên và công cụ`, tải packet nhỏ lên, gửi prompt
   và nhận phản hồi trong chat thật.
5. `gemini_web\session.json`, `raw_response.json`, screenshot và receipt được tạo;
   conversation URL khác trang `/app` trống và chat xuất hiện trong lịch sử.

## Kiểm tra follow-up cùng chat

Tạo một file feedback bên trong run, ví dụ
`<run_dir>\gemini_web\script\follow_up_prompt.txt`, với lỗi cụ thể như beat/field
cần sửa. Sau đó chạy:

```powershell
uv run python run_episode.py gemini-web continue --run "<run_dir>" --phase script --prompt-file "<run_dir>\gemini_web\script\follow_up_prompt.txt"
```

Kỳ vọng URL chat không đổi, không mở tab chat mới, lượt thứ hai xuất hiện sau lượt
đầu và receipt/response mới vẫn được ký bởi operator. Lượt thứ bảy phải bị chặn.

## Dọn phiên

Sau khi smoke hoặc phase FINAL đạt:

```powershell
uv run python run_episode.py gemini-web stop --run "<run_dir>"
```

Kỳ vọng Chrome operator đóng và `.local\gemini_operator_session.json` bị xóa. Nếu
Chrome/login/model gặp lỗi, không chạy stop; để cửa sổ mở, xử lý thủ công rồi chạy
lại lệnh tương ứng. Không tạo receipt, critic, screenshot hoặc verdict bằng tay.
