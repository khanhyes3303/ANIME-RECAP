# Anime Review MVP — Antigravity situation-first

Mỗi run xử lý đúng một tập anime. Antigravity là biên tập viên nội dung duy nhất; engine
cục bộ tạo TTS, timeline, EDL, proxy, kiểm định và render. Gemini Web không thuộc luồng
mặc định.

## Yêu cầu

Python 3.12+, `uv`, FFmpeg và FFprobe phải có sẵn trong `PATH`. Hệ thống không tự cài
thiếu sót; nó dừng và nêu chính xác công cụ người dùng cần cài.

## Khởi tạo

```powershell
uv sync --dev
uv run python run_episode.py start --anime "Ten Anime" --season 1 --episode 1 --video "D:\Tap01.mp4"
uv run python run_episode.py prepare --run "<duong_dan_run>"
```

`prepare` phân tích transcript, shot và frame rồi tạo task `STRUCTURE`. File duy nhất cần
gửi cho Antigravity là nội dung `PROMPT_GUI_ANTIGRAVITY.txt` trong run. Có thể in đường
dẫn chính xác mà không ghi đè prompt đặc thù bằng:

```powershell
uv run python run_episode.py prompt --run "<duong_dan_run>"
```

Sau đó gắn `teamwork-preview` và `goal`, gửi prompt một lần. Antigravity sẽ tự tiếp tục
mọi situation và verifier; người dùng chỉ xem proxy và chọn approve hoặc reject.

## Luồng mặc định gồm đúng 6 bước

```text
1. PHAN_TICH: Antigravity xem frame + transcript/SRT, xác định tình huống và hành động.
2. VIET_REVIEW: chọn đúng đoạn nguồn theo từng tình huống rồi viết lời review.
3. TAO_VOICE_VA_KHOP_CANH: tạo voice; mỗi cue chỉ dùng các shot được duyệt của cue đó
   và chọn tốc độ phát hợp lệ để lời khớp cảnh.
4. DUNG_VIDEO: dựng từng đoạn ngắn rồi nối thành proxy 7–12 phút.
5. KIEM_TRA: đo thời lượng, khoảng im lặng, âm lượng, đồng bộ và đối chiếu ngữ nghĩa.
6. CHO_NGUOI_DUNG_DUYET_PROXY: dừng để người dùng approve hoặc reject.
```

`next_action.json` và `operator_status.json` hiển thị `public_stage` theo sáu bước trên;
`stage` chi tiết vẫn được giữ để engine biết chính xác công việc nội bộ.

Mỗi cue phải dùng một cửa sổ shot liên tục, gọn, nằm trong evidence đã được duyệt. Engine
chỉ được chọn tốc độ trong giới hạn policy; nếu voice không vừa cảnh hoặc tạo hơn 1.200 ms
im lặng, nó trả `CUE_TIMELINE_DOES_NOT_FIT` để sửa đúng cue, không kéo cả tình huống và
không chèn cảnh chết. Proxy ngoài 420.000–720.000 ms hoặc có lỗi đo bằng máy sẽ bị chặn;
kết quả kiểm tra ngữ nghĩa không được quyền ghi đè lỗi máy.

Mỗi run được gắn với repository và commit engine đã tạo nó. Nếu chạy bằng checkout cũ
hoặc code không cùng lịch sử, lệnh dừng với `RUN_CODE_IDENTITY_MISMATCH`; hãy quay lại
đúng checkout hiện tại và chạy lại lệnh tuyệt đối ghi trong prompt. Không sao chép draft,
audit `MATCH/CLEAN` hay artifact từ run cũ để tiếp tục.

Mỗi job khai báo `task_kind`, `required_outputs` và `allowed_staging_dir`. Không dùng file
mẫu, task cũ, artifact trong `revisions` hoặc tài liệu lịch sử để đoán việc hiện tại.
Thành phẩm cuối nằm tại:

```text
Kho_Anime/<Anime>/Mua_XX/Tap_XXX/Thanh_pham/review_anime.mp4
```
