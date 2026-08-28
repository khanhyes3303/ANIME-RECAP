# Prompt giao một tập cho Antigravity

Bạn hãy xử lý **duy nhất một tập anime** trong file job sau:

```text
<ĐƯỜNG_DẪN_RUN>\cong_viec_antigravity.json
```

Đọc `D:\FINAL REVIEW ANIME\Bo_nao_Antigravity\GEMINI.md` trước khi làm. Thực hiện
liên tục trong một agent run:

```text
prepare → QUAN_SAT truth + scene_packets
→ validate truth/scene → VIET_KICH_BAN → validate script
→ audit script → TTS BV074_streaming
→ EDL tự sinh theo duration WAV thật → validate edl/voice-lock
→ render TTS-only → audit MP4 → package ZIP
```

Không hỏi người dùng duyệt giữa các bước. Scene là đơn vị kể chuyện, shot là đơn vị
cắt hình. Giữ shot `MUST_KEEP`, chỉ cắt `OPTIONAL`/`TRANSITION`. Không đổi cốt truyện,
không nhét chữ vào miệng nhân vật, không speed/freeze/loop, không dùng audio tiếng Anh
hoặc BGM. Nếu lỗi, sửa artifact đúng owner và lặp lại; sau ba vòng chưa đạt thì tạo
`CAN_CON_NGUOI_XU_LY`, không xuất PASS giả.
