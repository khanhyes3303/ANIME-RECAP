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
đúng `BV074_streaming`, dựng proxy. Mọi critic bắt buộc dùng operator Chrome hiển thị
được engine mở tại `https://gemini.google.com`, đúng Google AI Ultra, model `3.7 Flash`
và mode `Tư duy mở rộng`; người dùng tự đăng nhập và tự chọn model/mode, engine chỉ
đọc DOM xác nhận. Tải packet bất biến và trả JSON-only trong cùng một chat của run.
Chạy đúng ba lệnh sau, không thay bằng lệnh accept thủ công hay `validate critic-*`:

```powershell
uv run python run_episode.py gemini-web run --run "<run_dir>" --phase script
uv run python run_episode.py gemini-web run --run "<run_dir>" --phase proxy
uv run python run_episode.py gemini-web run --run "<run_dir>" --phase final
```

Nếu Gemini trả JSON/schema hoặc finding chưa đạt, tạo prompt feedback nằm bên trong
`<run_dir>` rồi gọi tối đa đến lượt thứ sáu:

```powershell
uv run python run_episode.py gemini-web continue --run "<run_dir>" --phase "<phase>" --prompt-file "<run_dir>\gemini_web\<phase>\follow_up_prompt.txt"
```

Lệnh `continue` luôn nối vào conversation URL hiện tại; không mở chat mới, không tải
lại trang nếu đúng chat đang mở và không upload lại file nếu feedback chỉ yêu cầu sửa.
Mỗi lượt phải đợi upload hoàn tất trước khi bấm Gửi, sau đó không tác động Chrome cho
đến khi Gemini trả lời xong. Không chạy hai lệnh `gemini-web run`/`continue` đồng thời
hoặc gọi lại ngay khi lượt trước chưa hoàn tất. Khi tập hoàn tất và audit PASS, dọn phiên:

Nếu Codex/người dùng yêu cầu bỏ chat lỗi và làm lại bằng một cuộc trò chuyện mới, chạy
đúng một lần `gemini-web new-chat --run "<run_dir>" --phase "<phase>"`. Không dùng
`continue` cho yêu cầu này. Chat mới phải upload lại full packet; các follow-up sau đó
mới tiếp tục trong chat vừa tạo.

```powershell
uv run python run_episode.py gemini-web stop --run "<run_dir>"
```

Trước khi phase FINAL và engine audit đạt, không được chạy `gemini-web stop`,
`Stop-Process`, `taskkill` hoặc kill Chrome dưới bất kỳ hình thức nào. Nếu engine yêu
cầu người dùng đăng nhập/chọn model nhưng cửa sổ không hiện, giữ nguyên phiên và chạy:

```powershell
uv run python run_episode.py gemini-web show --run "<run_dir>"
```

Chờ người dùng thao tác trên giao diện vừa hiện rồi chạy lại đúng phase; không xóa
session metadata, không tạo profile mới và không tự xử lý đăng nhập.

Không dùng Gemini API, MCP, tài khoản thường, model thấp hơn hoặc fallback. Không
được sinh critic hàng loạt bằng giá trị mặc định, tự khai PASS, tự viết verdict thay
Gemini, bỏ qua CAPTCHA/login hoặc sửa bộ não/code/test/dependency/Git/video nguồn.
Ở mỗi phase, để engine tự tạo và upload `operator_packet`; không tự ghi response, critic,
screenshot, receipt hoặc ledger. Không dùng FFmpeg/ImageMagick tạo ảnh phiên, không tự
khai account/model/READY. Không dùng lại response, ảnh hoặc receipt của run/phase khác.
Sau mỗi lệnh phải đọc `next_action.json`. Nếu chưa có binding Ultra, dừng để người
dùng đăng nhập và enroll; không tự nhập mật khẩu.

Khi hoàn tất, báo đường dẫn `review_anime.mp4`, tổng thời gian, cache hit/miss, beat đã
sửa và lỗi đã loại. Nếu engine chặn sau ba vòng hoặc cần đổi kiến trúc, ghi
`BRAIN_CHANGE_REQUESTED` với bằng chứng và dừng trung thực.
