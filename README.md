# Anime Review MVP

Dự án tối giản để Antigravity xử lý **mỗi lần đúng một tập anime dub tiếng Anh** và
xuất video review 7–12 phút chỉ có giọng TTS tiếng Việt `BV074_streaming`. Toàn bộ
audio nguồn bị loại khỏi thành phẩm; không BGM, không caption, không batch.

## Cài đặt

1. Cài Python 3.12+, [uv](https://docs.astral.sh/uv/) và FFmpeg/FFprobe trong `PATH`.
2. Tại thư mục dự án chạy `uv sync --dev`.
3. Đặt session dùng bởi TTS cũ trong biến môi trường, không ghi vào file:

   ```powershell
   $env:ANIME_RECAP_TIKTOK_SESSION = "SESSION_CUA_BAN"
   ```

TTS chạy từ máy local nhưng provider TikTok/CapCut vẫn cần session và kết nối tới
endpoint mà dự án cũ đang dùng. Engine không tự đổi provider hoặc đổi giọng khi lỗi.

## Chạy một tập

Giao đúng một video cho Antigravity:

```powershell
uv run python run_episode.py start --anime "Ten Anime" --season 1 --episode 1 --video "D:\Tap01.mp4"
```

Antigravity đọc [GEMINI.md](Bo_nao_Antigravity/GEMINI.md) và file
`next_action.json` trong thư mục run được in ra. Nó tự gọi tuần tự các lệnh nội bộ
`prepare`, `validate truth`, `validate scene`, `validate script`, `audit`, `tts`,
`validate edl`, `render`, `audit video`, `package`; người dùng không phải chạy từng
lệnh bằng tay. Không đưa nhiều tập vào cùng một run.

Trong pipeline, **scene** là đơn vị kể chuyện và **shot** là các đoạn hình bên trong
scene. Antigravity tạo `scene_packets.json`, đánh dấu shot chính/phụ và chia các beat
hành động. Sau khi TTS được tạo, engine đo WAV thật và sinh EDL; voice cue có thể phủ
nhiều shot nhưng luôn thuộc đúng scene. Shot `MUST_KEEP` không bị cắt chỉ vì lời ngắn.

Thành phẩm nằm tại:

```text
Kho_Anime/<Anime>/Mua_XX/Tap_XXX/Thanh_pham/review_anime.mp4
```

ZIP gửi ChatGPT Web nằm trong `Goi_gui_ChatGPT_Web`. ZIP không chứa byte video lớn;
nó chứa báo cáo, artifact kiểm định, đường dẫn tuyệt đối và SHA-256 của nguồn/thành
phẩm. Sau khi đóng gói, tài nguyên trong đúng thư mục run tạm được dọn; nguồn và hồ sơ
tập vẫn được giữ nguyên.
