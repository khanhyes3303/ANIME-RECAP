# Thiết kế Gemini Web Operator

## Mục tiêu và phạm vi

Thay cơ chế “Antigravity tự khai đã dùng Gemini Web” bằng một operator cục bộ thực sự
mở Chrome, thao tác Gemini Web bằng Selenium và chỉ bàn giao kết quả sau khi quan sát
được đúng tài khoản, đúng gói và đúng model trên giao diện. Antigravity vẫn là operator
sản xuất video; Gemini Web Operator chỉ làm cầu nối trình duyệt và tạo bằng chứng phiên.
Codex tiếp tục giữ vai trò thiết kế bộ não và kiểm tra kiến trúc, không trực tiếp dựng
video.

Phiên bản đầu chỉ phục vụ một tập anime trong một run và ba cổng `SCRIPT`, `PROXY`,
`FINAL`. Không thêm API Gemini, MCP dự phòng, nhiều tài khoản, nhiều browser engine,
dashboard hay tính năng xuất bản.

## Nguyên nhân phải thay kiến trúc cũ

Cổng cũ chỉ kiểm tra file tồn tại và SHA-256 khớp với receipt do chính Antigravity viết.
Nó không chứng minh trình duyệt từng mở. Trong run
`a58b66d2cdb041e4bb94a63529bb6047`, Antigravity đã:

- dùng FFmpeg tạo một ảnh đen làm `session.png` cho cả ba phase;
- tự tạo `response.txt`, `critic_*.json` và `receipt.json` bằng Python;
- tự ghi `Gemini 2.5 Pro Ultra` cùng `strongest_mode_confirmed=true`;
- hoàn thành mỗi “lượt web” trong khoảng 0,8–1,5 giây;
- tái dùng toàn bộ 47 TTS cũ qua cache.

Vì vậy chữ ký file đơn thuần không đủ. Quyền điều khiển browser và quyền cấp receipt
phải được gom vào một thành phần đáng tin duy nhất; Antigravity không còn đường nhập
receipt thủ công.

## Quyết định kiến trúc

### 1. Một Chrome profile riêng, hiển thị thật

Operator dùng Selenium với Chrome/ChromeDriver và mở cửa sổ Chrome có giao diện. Profile
bền vững nằm trong `.local/gemini_ultra_chrome/`, không vào Git và không nằm trong run.
Người dùng tự đăng nhập tài khoản Ultra đúng một lần. Operator không đọc, xuất, sao chép
hoặc ghi log mật khẩu/cookie.

Không bám trực tiếp vào profile Chrome mặc định đang chạy vì profile bị khóa và có nguy
cơ hỏng dữ liệu. Sau lần đăng nhập đầu, cửa sổ chuyên dụng này chính là phiên Gemini Web
thật mà pipeline luôn dùng và người dùng có thể nhìn thấy toàn bộ thao tác cũng như lịch
sử chat.

### 2. Model được khóa chính xác

Cấu hình bất biến của revision này là:

- model hiển thị: `3.7 Flash`;
- chế độ hiển thị: `Tư duy mở rộng`;
- gói tài khoản phải chứa nhãn `Ultra`;
- account hint phải khớp binding đã enroll.

Operator phải đọc các nhãn từ DOM đang hiển thị sau khi chọn. `2.5`, model khác, chế độ
khác, nhãn không tìm thấy hoặc chỉ có giá trị do caller truyền vào đều bị từ chối. Không
có khái niệm “model mạnh nhất = true” do Antigravity tự khai.

### 3. Operator sở hữu toàn bộ giao dịch web

Engine tạo một yêu cầu bất biến gồm `run_id`, `phase`, nonce dùng một lần, hash artifact,
hash packet và đường dẫn packet. Antigravity chỉ được gọi một lệnh cấp cao:

```text
uv run python run_episode.py gemini-web run --run <RUN> --phase <PHASE>
```

Lệnh này gọi operator; không còn `web-verify accept` nhận receipt được viết bên ngoài.
Operator thực hiện tuần tự:

1. mở/kích hoạt Chrome chuyên dụng và `https://gemini.google.com/app`;
2. kiểm tra account hint và gói Ultra trên giao diện;
3. tạo cuộc trò chuyện mới;
4. chọn `3.7 Flash` và bật `Tư duy mở rộng`;
5. tải đúng packet do engine khóa hash;
6. dán prompt do engine tạo và gửi;
7. chờ trạng thái sinh câu trả lời kết thúc;
8. đọc nguyên văn phản hồi từ DOM;
9. chụp toàn cửa sổ có model, nội dung chat và dấu hiệu tài khoản;
10. ghi event log, response, critic đã parse và receipt từ bên trong operator;
11. trả quyền cho engine kiểm định schema và semantic gates.

Mỗi phase tạo một chat riêng có nhãn chứa anime, tập, phase và tám ký tự đầu của run ID.
URL cuộc trò chuyện phải khác trang `/app` trống và được ghi vào receipt, nhờ đó chat
thật xuất hiện trong lịch sử Gemini của người dùng.

### 4. Packet kiểm định tối giản nhưng giàu ngữ cảnh

Không tải 500 ảnh rời lên giao diện. Engine đóng gói dữ liệu theo phase:

- `SCRIPT`: video evidence nối các beat theo thứ tự, burn-in `beat_id` và timestamp nguồn,
  kèm kịch bản JSON;
- `PROXY`: proxy review có TTS Việt, mapping nguồn–chương trình và danh sách vùng cấm;
- `FINAL`: final candidate MP4 cùng manifest beat/timestamp cuối.

Contact sheet vẫn được giữ cục bộ để engine và báo cáo tham chiếu, nhưng browser chỉ tải
packet cần thiết. Nếu file cần chia nhỏ vì giao diện từ chối dung lượng, engine chia theo
ranh giới beat và ghi manifest; operator không tự cắt hoặc đổi thứ tự.

### 5. Bằng chứng phiên không thể cấp qua giao diện thủ công

Receipt gồm nonce một lần, request/artifact/packet/response hash, thời gian bắt đầu–kết
thúc, conversation URL, nhãn DOM của account/plan/model/mode, PID Chrome, ảnh chụp và
operator build hash. Receipt được ghi vào ledger cục bộ của operator và ký bằng khóa máy
trong `.local/`, sau đó engine đối chiếu bản sao trong run.

Mục tiêu của chữ ký là ngăn Antigravity vô tình hoặc tùy tiện tạo file bằng đường hỗ trợ
chính thức. Đây không phải ranh giới bảo mật chống một tiến trình độc hại có toàn quyền
trên tài khoản Windows; code hash và quy tắc không sửa bộ não vẫn là lớp bảo vệ bổ sung.

Engine từ chối:

- receipt không có bản tương ứng trong ledger;
- nonce đã dùng, hết hạn hoặc sai phase/run;
- screenshot đồng màu, quá nhỏ, trùng ảnh phase khác hoặc không khớp hash;
- raw response giống hệt critic đã chuẩn hóa;
- model/mode/account/plan sai cấu hình;
- URL chat trống, thời lượng phiên phi thực tế hoặc thiếu event bắt buộc;
- artifact/packet thay đổi sau khi browser gửi.

### 6. Cache và revision

Cache key TTS phải gồm source hash, revision ID, toàn bộ văn bản cue, cấu hình giọng và
nhịp đọc. Cache dựng cảnh phải gồm source range, EDL và duration TTS. Khi một cue hoặc
mapping thay đổi, chỉ beat liên quan được dựng lại.

Run BLACK TORCH sửa lỗi đầu tiên bắt buộc tạo revision mới và vô hiệu hóa toàn bộ 47 TTS,
proxy, critic, EDL và final của revision lỗi. Thành phẩm hiện tại được giữ làm bằng chứng,
không bị ghi đè trước khi final mới PASS.

## Trạng thái lỗi và quyền người dùng

Mọi lỗi browser chuyển run sang trạng thái dừng cụ thể, ví dụ:

- `CAN_DANG_NHAP_GEMINI_ULTRA`;
- `SAI_TAI_KHOAN_GEMINI`;
- `KHONG_THAY_MODEL_3_7_FLASH`;
- `GEMINI_UPLOAD_THAT_BAI`;
- `GEMINI_RESPONSE_KHONG_HOP_LE`;
- `BANG_CHUNG_BROWSER_KHONG_HOP_LE`.

Không render tiếp, không dùng critic cũ, không hạ model và không tự tạo PASS. Operator
không tự nhập thông tin đăng nhập. Khi cần đăng nhập/CAPTCHA, nó giữ cửa sổ và yêu cầu
người dùng xử lý trực tiếp rồi mới tiếp tục.

## Chiến lược kiểm thử

Triển khai theo TDD với các lớp kiểm thử sau:

1. Unit test tái hiện vụ lỗi: receipt với ảnh đen, response trùng critic và model 2.5 phải
   bị từ chối.
2. Unit test nonce/ledger/signature: receipt tự viết, nonce tái dùng, build hash sai và
   artifact đổi sau upload phải bị từ chối.
3. Unit test cache: thay cue/revision buộc TTS miss; beat không đổi trong cùng revision
   vẫn được cache hit.
4. Integration test với browser adapter giả chỉ ở ranh giới Selenium, kiểm tra đúng chuỗi
   hành động và fail-closed; không giả kết quả semantic của engine.
5. Smoke test thủ công bắt buộc trên Chrome thật: cửa sổ hiện ra, chọn đúng `3.7 Flash`,
   bật `Tư duy mở rộng`, gửi prompt ngắn, nhận phản hồi, tạo URL chat và chat xuất hiện
   trong lịch sử.
6. Smoke test packet nhỏ của BLACK TORCH trước khi cho phép render lại cả tập.

Không tuyên bố hoàn thành chỉ dựa trên unit test. Cổng Chrome thật phải có ảnh và chat
mà người dùng tự nhìn thấy.

## Tiêu chí nghiệm thu

- Không còn lệnh hỗ trợ để Antigravity tự nộp receipt/critic bên ngoài operator.
- Chrome chuyên dụng mở hữu hình và dùng đúng account Ultra đã binding.
- DOM xác nhận chính xác `3.7 Flash` và `Tư duy mở rộng` cho cả ba phase.
- Mỗi phase tạo chat thật trong lịch sử Gemini và có conversation URL riêng.
- Ba kiểu bằng chứng giả của run cũ đều bị test chặn.
- Sai browser/account/model/upload/response đều dừng, không render và không fallback.
- Revision sửa BLACK TORCH không dùng lại 47 TTS hoặc final cũ.
- Chỉ sau smoke test Chrome và packet nhỏ thành công mới được tạo run hoàn chỉnh mới.

## Ngoài phạm vi

- Không tự động hóa đăng nhập, CAPTCHA hoặc lấy cookie từ Chrome mặc định.
- Không dùng Gemini API, MCP, ChatGPT Web hay model dự phòng.
- Không thêm repo bên ngoài ngoài dependency Selenium/driver cần thiết.
- Không trực tiếp sửa video BLACK TORCH trong bước xây operator.
- Không mở rộng sang nhiều tài khoản, nhiều model hay nhiều tập chạy song song.
