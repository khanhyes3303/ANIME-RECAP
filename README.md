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

## Luồng duy nhất

```text
prepare
→ Antigravity chia situation index từ transcript + frame
→ engine chấp nhận index
→ Antigravity biên tập tuần tự từng situation
→ local validator tạo/kiểm TTS + semantic timeline + EDL
→ proxy
→ người dùng duyệt
→ final render + engine audit
```

Mỗi job khai báo `task_kind`, `required_outputs` và `allowed_staging_dir`. Không dùng file
mẫu, task cũ, artifact trong `revisions` hoặc tài liệu lịch sử để đoán việc hiện tại.
Thành phẩm cuối nằm tại:

```text
Kho_Anime/<Anime>/Mua_XX/Tap_XXX/Thanh_pham/review_anime.mp4
```
