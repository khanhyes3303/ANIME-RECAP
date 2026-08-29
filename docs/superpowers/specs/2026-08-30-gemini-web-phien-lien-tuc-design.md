# Gemini Web Operator — Phiên liên tục theo từng tập

## Mục tiêu

Cho phép Antigravity làm việc với Gemini Web như một phiên cộng tác thật trong
suốt một tập anime: mở Chrome có giao diện, chờ người dùng đăng nhập và chọn
model, gửi video/file/prompt, đọc phản hồi, trao đổi bổ sung khi cần, rồi chỉ
bàn giao kết quả sau khi kiểm định đạt.

Codex giữ vai trò kiến trúc và kiểm định. Antigravity vẫn là operator sản xuất
video. Gemini Web chỉ được truy cập qua Chrome/Selenium do operator quản lý.

## Phạm vi và điều không làm

- Một run chỉ đại diện cho một anime, một mùa và một tập.
- Một Chrome profile riêng tại `.local/gemini_ultra_chrome/`; không dùng profile
  Chrome thường của người dùng.
- Không dùng Gemini API, MCP dự phòng, cookie export, mật khẩu tự động, nhiều
  tài khoản, nhiều browser engine hoặc dashboard.
- Không để Codex dựng video. Không để Antigravity tự tạo critic, receipt hoặc
  verdict khi Gemini Web chưa trả kết quả thật.

## Luồng người dùng chuẩn

1. Antigravity gọi `gemini-web run --run <RUN> --phase <PHASE>`.
2. Operator khởi động hoặc gắn vào Chrome chuyên dụng ở chế độ visible. Nếu
   chưa có phiên hợp lệ, cửa sổ được giữ mở và hiển thị hướng dẫn để người dùng
   tự đăng nhập tài khoản Ultra.
3. `gemini-web enroll` là lần người dùng xác nhận thủ công tài khoản cho profile
   Chrome chuyên dụng; engine chỉ lưu hash và account hint đã che. Ở các phiên
   sau, operator yêu cầu DOM Gemini có account control và nhãn Ultra, rồi đối
   chiếu với binding của profile. Người dùng tự chọn `3.7 Flash` và `Tư duy mở
   rộng`; operator không bấm đổi model/mode.
4. Ở phase đầu, operator mở một chat mới. Ở các phase sau, operator điều hướng
   về `conversation_url` đã ghi trong run và tiếp tục đúng chat đó.
5. Operator tải đúng packet đã khóa hash, gửi prompt của phase, chờ câu trả lời
   hoàn tất và đọc nguyên văn DOM.
6. Antigravity có thể gửi các prompt follow-up trong cùng chat để Gemini sửa
   JSON, bổ sung bằng chứng hoặc giải thích điểm chưa khớp. Mỗi lượt được ghi
   lại; không tạo chat mới và không tự sửa nội dung phản hồi.
7. Khi response đạt schema, coverage, hình–lời–timestamp và các cổng semantic,
   operator ghi receipt có bằng chứng thật. Khi chưa đạt giới hạn lượt, nó tiếp
   tục hội thoại. Khi hết lượt, run dừng `CAN_CON_NGUOI_XU_LY`.
8. Sau khi phase FINAL được chấp nhận, operator đóng Chrome và xóa metadata
   phiên tạm. Nếu gặp lỗi cần người xử lý, cửa sổ vẫn mở để người dùng sửa rồi
   chạy lại; không đóng sớm như lỗi hiện tại.

## Thành phần và giao diện

### `SeleniumGeminiPage`

- `wait_until_ready()` ưu tiên email nếu Gemini thực sự đưa email vào DOM. Khi
  email chỉ nằm trong menu Chrome ngoài DOM, nó dùng binding đã enroll một lần
  và vẫn bắt buộc account control, nhãn Ultra, model và mode hiện trên DOM.
- `send_prompt(prompt)` và `wait_for_response()` thao tác từng lượt trong chat.
- `open_new_chat()` chỉ được gọi khi run chưa có conversation URL.
- `open_conversation(url)` tiếp tục chat đã lưu.
- Không còn thao tác `select_model()` hoặc `select_mode()` tự động trong luồng
  production.

### `GeminiSessionRegistry`

Lưu metadata không nhạy cảm trong `.local/gemini_operator_session.json`:

```json
{
  "run_id": "...",
  "chrome_pid": 1234,
  "debugger_address": "127.0.0.1:9222",
  "conversation_url": "https://gemini.google.com/app/...",
  "started_at": "..."
}
```

Registry chỉ cho phép attach khi PID/debugger còn sống và run ID khớp. Không ghi
email đầy đủ, mật khẩu, cookie hay nội dung nhạy cảm vào metadata. `stop` hoặc
phase FINAL thành công sẽ đóng process, giải phóng lock và xóa metadata.

### `GeminiWebOperator`

Session runner mở một browser session duy nhất cho run. Nó trả về danh sách
turns (prompt/response hash, thời gian, URL) và response cuối cùng. Receipt phải
ghi conversation URL duy nhất của run, số lượt, model/mode/account đã đọc từ DOM,
PID Chrome và screenshot thật.

## Kiểm soát hội thoại

- Mỗi phase có tối đa 6 lượt, gồm lượt prompt ban đầu và tối đa 5 follow-up.
- Follow-up chỉ được tạo từ lỗi kiểm định cụ thể (JSON/schema/coverage/timestamp
  hoặc mismatch hình–lời), không được viết lại cốt truyện hay nhét chữ vào miệng
  nhân vật.
- Nội dung follow-up phải nêu beat/shot/field lỗi và yêu cầu Gemini sửa đúng dữ
  kiện nguồn; không chấp nhận câu trả lời chỉ nói “đã sửa”.
- Nếu Gemini trả response hợp lệ nhưng semantic audit thất bại, Antigravity gửi
  bằng chứng lỗi trong cùng chat; nếu vẫn thất bại sau 6 lượt thì dừng để người
  dùng/Codex quyết định.

## Trạng thái và lỗi

- `CAN_DANG_NHAP_GEMINI_ULTRA`: chưa đọc được account/email; giữ Chrome mở.
- `SAI_TAI_KHOAN_GEMINI`: email hash không khớp binding; không gửi file.
- `KHONG_THAY_MODEL_3_7_FLASH`: model/mode người dùng chọn chưa đúng; chờ người
  dùng chỉnh trên cửa sổ, không tự đổi.
- `GEMINI_UPLOAD_THAT_BAI`, `GEMINI_RESPONSE_KHONG_HOP_LE` hoặc
  `BANG_CHUNG_BROWSER_KHONG_HOP_LE`: giữ phiên để retry an toàn, không cấp PASS.
- Chrome chết hoặc metadata stale: đánh dấu phiên hỏng, dọn lock an toàn, cho
  phép lần chạy kế tiếp mở profile chuyên dụng lại.

## Dòng dữ liệu và lưu trữ

- Packet vẫn nằm dưới `run/gemini_web/<phase>/operator_packet/` và được khóa hash
  trước khi upload.
- Response thô từng lượt nằm dưới `run/gemini_web/<phase>/raw_response.json`;
  critic chuẩn hóa nằm ở file riêng. Không dùng lại response/critic cũ của
  revision khác.
- Conversation URL được lưu trong run manifest và được kiểm tra thuộc
  `https://gemini.google.com/app/<chat-id>`.
- Tài nguyên Chrome tạm thuộc `.local/`, không trộn vào thư mục anime và được
  dọn sau FINAL hoặc `stop`.

## Kiểm thử và nghiệm thu

1. Unit test: selector account đa dạng; chờ login/model thủ công; không gọi
   selector tự chọn model; timeout giữ đúng mã lỗi.
2. Unit test: session registry attach đúng PID/run, từ chối stale/mismatch và
   dọn metadata khi stop.
3. Unit test: phase sau dùng `open_conversation()` thay vì `open_new_chat()`;
   follow-up giữ nguyên URL và bị chặn sau 6 lượt.
4. Integration fake-browser: thứ tự open/verify/upload/send/wait/follow-up và
   fail-closed khi file hoặc response sai.
5. Smoke thủ công bắt buộc: Chrome thật hiện ra; người dùng đăng nhập Ultra,
   chọn `3.7 Flash` + `Tư duy mở rộng`; Antigravity gửi một packet nhỏ; Gemini
   trả lời; lượt follow-up xuất hiện trong cùng chat và chat có trong lịch sử.
6. Chỉ sau smoke đạt mới chạy lại tập BLACK TORCH; revision mới không tái sử
   dụng TTS/EDL/final của bản lỗi.

## Tiêu chí hoàn thành

- Người dùng nhìn thấy và điều khiển được Chrome operator.
- Antigravity không tự chọn model, không dùng Chrome thường và không tự tạo
  bằng chứng Gemini.
- Toàn bộ SCRIPT/PROXY/FINAL của một run dùng một conversation URL liên tục.
- Có thể trao đổi nhiều lượt có giới hạn, mọi lượt đều có hash/thời gian và
  response cuối chỉ được chấp nhận khi tất cả cổng kiểm định PASS.
- Lỗi đăng nhập hoặc model không còn làm cửa sổ biến mất trước khi người dùng
  xử lý.
