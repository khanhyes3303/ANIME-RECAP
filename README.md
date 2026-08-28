# Anime Review MVP — phương án B

Pipeline tối giản cho mỗi lần đúng một tập anime dub tiếng Anh. Thành phẩm dài 7–12
phút, chỉ có TTS tiếng Việt `BV074_streaming`; không audio tiếng Anh, BGM, caption,
batch, ZIP hoặc ChatGPT Web.

## Phân vai

- Antigravity xem nguồn và tạo truth, scene packet, lời review nháp, audit nháp.
- Codex xem frame, viết lại lời cuối, khóa từng câu với đúng vùng hình, tạo TTS/EDL,
  kiểm tra candidate và lập semantic review.
- Engine local render và tự tính PASS kỹ thuật/ngữ nghĩa từ bằng chứng; không tin cờ
  PASS do Antigravity viết.
- Người dùng chuyển prompt/báo cáo và chỉ cần xem MP4 cuối.

## Cài đặt

1. Cài Python 3.12+, `uv`, FFmpeg và FFprobe trong `PATH`.
2. Chạy `uv sync --dev`.
3. Đặt session TTS trong biến môi trường:

```powershell
$env:ANIME_RECAP_TIKTOK_SESSION = "SESSION_CUA_BAN"
```

TTS chạy từ máy local với đúng voice/provider cũ; engine không tự đổi giọng khi lỗi.

## Bắt đầu một tập

```powershell
uv run python run_episode.py start --anime "Ten Anime" --season 1 --episode 1 --video "D:\Tap01.mp4"
```

Nếu tập đã có thành phẩm và cần làm bản sửa:

```powershell
uv run python run_episode.py start --anime "Ten Anime" --season 1 --episode 1 --video "D:\Tap01.mp4" --revision
```

Antigravity nhận prompt trong `Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md` và dừng ở
`CODEX_BIEN_TAP`. Từ đó Codex thực hiện:

```text
khoa_cau_canh.json → lock → TTS từng span → EDL khóa
→ render review_candidate.mp4 → kiểm tra anchor đầu/giữa/cuối
→ codex_semantic_review.json → engine audit → xuất bản an toàn
```

Mỗi span là một câu/ý gắn với một hành động hoặc phản ứng. Range hình do Codex chọn
được giữ nguyên; TTS lệch quá 80 ms phải sửa, không trim shot cơ học. Segment dưới
500 ms bị chặn trừ ngoại lệ hành động được Codex đánh dấu.

Candidate nằm trong run và không ghi đè video hiện tại. Chỉ khi engine audit PASS,
video cũ được sao lưu vào `Bao_cao/phien_ban_cu` rồi candidate mới trở thành:

```text
Kho_Anime/<Anime>/Mua_XX/Tap_XXX/Thanh_pham/review_anime.mp4
```

Run tạm được giữ nguyên để kiểm tra; pipeline không tự dọn tài nguyên.
