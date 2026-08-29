# Anime Review MVP — Antigravity-first

Pipeline tối giản cho một tập anime dub tiếng Anh mỗi run. Antigravity tự phân tích,
viết review, tạo TTS, dựng proxy, tự phản biện và render video cuối. Codex chỉ thiết
kế/sửa bộ não sau phản hồi; không biên tập từng tập.

Thành phẩm dài 7–12 phút, chỉ có TTS Việt `BV074_streaming`; không audio nguồn, BGM,
caption, batch, ZIP hoặc ChatGPT Web.

## Cài đặt

Yêu cầu Python 3.12+, `uv`, FFmpeg và FFprobe trong `PATH`:

```powershell
uv sync --dev
$env:ANIME_RECAP_TIKTOK_SESSION = "SESSION_CUA_BAN"
```

## Tạo run cho một tập

```powershell
uv run python run_episode.py start --anime "Ten Anime" --season 1 --episode 1 --video "D:\Tap01.mp4"
```

Nếu tập đã có thành phẩm, thêm `--revision`. Sau khi chạy `prepare`, sinh prompt đã
gắn đúng đường dẫn:

```powershell
uv run python run_episode.py prompt --run "<đường_dẫn_run>"
```

Chỉ dán nội dung tệp `PROMPT_GUI_ANTIGRAVITY.txt` được in ra. Không dán trực tiếp
`Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md` vì đó là mẫu còn placeholder.

```text
prepare → truth/scene → atomic storyboard → critic script → TTS cache
→ atomic EDL → proxy 360p → critic video → final render → engine audit
```

Beat lỗi được sửa riêng; cache nằm trong
`Kho_Anime/<Anime>/Mua_XX/Tap_XXX/_Cache`. Thành phẩm ở:

```text
Kho_Anime/<Anime>/Mua_XX/Tap_XXX/Thanh_pham/review_anime.mp4
```

Antigravity không được sửa bộ não, code, dependency hoặc Git. Khi cần đổi kiến trúc,
nó báo `BRAIN_CHANGE_REQUESTED` để Codex xử lý.
