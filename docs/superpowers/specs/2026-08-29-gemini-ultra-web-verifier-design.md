# Gemini Ultra Web Verifier Design

## Quyết định đã khóa

Pipeline chỉ dùng một đường kiểm định thị giác: Antigravity Browser Agent mở
`https://gemini.google.com` trong một profile Chrome riêng và dùng đúng tài khoản
Google Ultra của chủ dự án. Không dùng Gemini API, tài khoản thường, model rẻ hơn,
Playwright MCP dự phòng hay cơ chế tự hạ cấp.

PowerShell chỉ được phép khởi động profile/trình duyệt. Người dùng tự đăng nhập lần
đầu; hệ thống không nhận, đọc, xuất hoặc lưu mật khẩu/cookie vào dự án.

## Cổng xác nhận phiên Ultra

Trước mỗi lượt kiểm định, Browser Agent phải:

1. mở Gemini Web trong profile riêng;
2. xác nhận đang đăng nhập đúng tài khoản do người dùng chỉ định;
3. xác nhận giao diện đang cho phép chọn chế độ/model mạnh nhất thuộc gói Ultra;
4. chọn chế độ/model đó và lưu ảnh chụp bằng chứng vào run hiện tại;
5. ghi biên nhận gồm thời gian, tên chế độ hiển thị và đường dẫn ảnh bằng chứng.

Không ghi địa chỉ email đầy đủ vào log công khai; chỉ lưu định danh đã che. Nếu
không xác nhận được một trong các điều kiện trên, stage chuyển sang
`CAN_NGUOI_DUNG_DANG_NHAP_ULTRA` và dừng. Không render/publish, không fallback.

## Luồng kiểm định hình–lời

1. Engine tạo contact sheet dày theo từng beat, gồm biên đầu/cuối, thời điểm hành
   động chính và mẫu trung gian; mọi ảnh có timestamp nguồn và chương trình.
2. Browser Agent tạo chat Gemini Web mới cho lượt kiểm định, tải đúng contact sheet,
   script cue và manifest beat lên.
3. Prompt bắt Gemini trả JSON theo schema cố định cho từng beat: hình quan sát được,
   nội dung voice, verdict `MATCH`, `VOICE_EARLY`, `VOICE_LATE`, `WRONG_VISUAL`,
   `EXCLUDED_CONTENT` hoặc `UNCERTAIN`, kèm timestamp bằng chứng.
4. Engine lưu nguyên phản hồi, ảnh chụp giao diện và hash của request/evidence vào
   run. Antigravity không được tự viết thay phản hồi kiểm định.
5. Chỉ beat `MATCH` mới được qua. Mọi verdict khác được sửa và gửi kiểm định lại;
   quá giới hạn vòng sửa thì dừng để báo cáo, không xuất PASS giả.
6. Final candidate phải qua thêm một lượt Gemini Ultra Web sau render. Intro,
   opening, ending, title card sai chỗ hoặc voice lệch cảnh đều là lỗi chặn.

## Fail-closed và tính tối giản

- Chỉ một profile, một tài khoản Ultra, một Browser Agent và một schema phản hồi.
- Không mở song song nhiều phiên dùng chung profile.
- Phiên hết hạn, CAPTCHA, upload lỗi, sai tài khoản, không thấy model mạnh nhất,
  response thiếu beat hoặc JSON sai đều dừng để người dùng xử lý.
- Kết quả Gemini không thay thế các khóa cứng của engine: vùng cấm OP/ED/intro,
  timestamp, evidence membership, revision isolation và hash thành phẩm mới.
- Chỉ gửi contact sheet/clip kiểm định cần thiết, không tải cả thư viện anime lên web.

## Điểm người dùng phải tham gia

Chỉ có một bước bắt buộc: khi profile Chrome riêng được mở lần đầu hoặc phiên đăng
nhập hết hạn, người dùng tự đăng nhập đúng tài khoản Ultra và xác nhận đã xong.
Sau đó pipeline có thể tiếp tục tự động.

## Tiêu chí nghiệm thu

- Không thể chạy kiểm định nếu thiếu biên nhận phiên Ultra.
- Không thể PASS nếu thiếu verdict cho bất kỳ beat nào.
- Không thể publish khi còn intro/OP/ED hoặc verdict khác `MATCH`.
- Một revision mới không được dùng lại critic, contact sheet, TTS/EDL hoặc final của
  revision cũ nếu input liên quan đã thay đổi.
- Báo cáo cuối liên kết được request, evidence, phản hồi Gemini Web và final hash.
