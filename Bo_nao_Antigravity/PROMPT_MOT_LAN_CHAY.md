# Prompt một lần chạy Antigravity

Xử lý duy nhất tập anime trong job:

```text
<ĐƯỜNG_DẪN_RUN>\cong_viec_antigravity.json
```

Đọc toàn bộ `D:\FINAL REVIEW ANIME\Bo_nao_Antigravity\GEMINI.md`, sau đó tiếp tục từ
stage hiện tại đến `HOAN_THANH` trong một agent run. Bạn là operator thực hiện video;
không dừng để giao Codex biên tập.

Phải mở thật video/frame/clip và toàn bộ evidence do engine tạo; tạo atomic storyboard
một hành động/phản ứng mỗi beat, dùng producer và critic context khác nhau, tạo TTS
đúng `BV074_streaming`, dựng proxy. Mọi critic bắt buộc dùng Browser Agent mở
`https://gemini.google.com` trong profile Chrome riêng đã đăng nhập đúng Google AI
Ultra; chọn mode/model mạnh nhất, tạo chat mới, tải contact sheet và trả JSON-only.
Chạy đúng ba cặp lệnh sau, không thay bằng `validate critic-*`:

```powershell
uv run python run_episode.py web-verify prepare --run "<run_dir>" --phase script
uv run python run_episode.py web-verify accept --run "<run_dir>" --phase script
uv run python run_episode.py web-verify prepare --run "<run_dir>" --phase proxy
uv run python run_episode.py web-verify accept --run "<run_dir>" --phase proxy
uv run python run_episode.py web-verify prepare --run "<run_dir>" --phase final
uv run python run_episode.py web-verify accept --run "<run_dir>" --phase final
```

Không dùng Gemini API, MCP, tài khoản thường, model thấp hơn hoặc fallback. Không
được sinh critic hàng loạt bằng giá trị mặc định, tự khai PASS, tự viết verdict thay
Gemini, bỏ qua CAPTCHA/login hoặc sửa bộ não/code/test/dependency/Git/video nguồn.
Ở mỗi phase, đọc `gemini_web/<phase>/request.json`, upload đúng artifact và toàn bộ
`evidence_paths`, lưu nguyên phản hồi vào `response.txt`, JSON theo schema vào đường
`critic_<phase>.json`, ảnh phiên vào `screenshots/session.png` và ghi `receipt.json`
đủ hash SHA-256. Không dùng lại response, ảnh hoặc receipt của run/phase khác.
Sau mỗi lệnh phải đọc `next_action.json`. Nếu chưa có binding Ultra, dừng để người
dùng đăng nhập và enroll; không tự nhập mật khẩu.

Khi hoàn tất, báo đường dẫn `review_anime.mp4`, tổng thời gian, cache hit/miss, beat đã
sửa và lỗi đã loại. Nếu engine chặn sau ba vòng hoặc cần đổi kiến trúc, ghi
`BRAIN_CHANGE_REQUESTED` với bằng chứng và dừng trung thực.
