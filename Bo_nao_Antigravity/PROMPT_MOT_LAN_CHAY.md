# Prompt giao một tập cho Antigravity

Bạn hãy xử lý **duy nhất một tập anime** trong file job sau:

```text
<ĐƯỜNG_DẪN_RUN>\cong_viec_antigravity.json
```

Đọc `D:\FINAL REVIEW ANIME\Bo_nao_Antigravity\GEMINI.md` trước khi làm. Thực hiện
liên tục trong một agent run:

`GEMINI.md`, mã nguồn, test, spec, plan, Git và video nguồn là chỉ đọc. Chỉ ghi đúng
artifact trong `required_outputs` và file tạm trong `run_dir`. Không tự sửa bộ não,
prompt, validator, voice/provider hoặc điều kiện PASS; nếu thấy cần thay đổi, ghi
`BRAIN_CHANGE_REQUESTED` và dừng ở báo cáo.

```text
prepare → QUAN_SAT truth + scene_packets
→ validate truth/scene → VIET_KICH_BAN → validate script
→ audit script → TTS BV074_streaming
→ EDL tự sinh theo duration WAV thật → validate edl/voice-lock
→ render TTS-only → audit MP4 → DỪNG VÀ BÁO CÁO
```

Nếu `run_state.json` đã ở `QUAN_SAT` (ví dụ run đã được prepare từ trước), bỏ qua
`prepare` và bắt đầu từ việc tạo `su_that_tap_phim.json` cùng `scene_packets.json`.

Không hỏi người dùng duyệt giữa các bước. Scene là đơn vị kể chuyện, shot là đơn vị
cắt hình. Giữ shot `MUST_KEEP`, chỉ cắt `OPTIONAL`/`TRANSITION`. Không đổi cốt truyện,
không nhét chữ vào miệng nhân vật, không speed/freeze/loop, không dùng audio tiếng Anh
hoặc BGM. Nếu lỗi, sửa artifact đúng owner và lặp lại; sau ba vòng chưa đạt thì tạo
`CAN_CON_NGUOI_XU_LY`, không xuất PASS giả.

Các loop nội bộ bắt buộc trong cùng agent run:

1. OBSERVER: mở video theo từng đoạn, lập event/shot có timestamp và bằng chứng.
2. WRITER: chọn cảnh có giá trị và viết cue từ đúng beat; cảnh thường chỉ để lấp thời
   lượng phải bỏ.
3. ADVERSARIAL_VERIFIER: mở lại từng clip nguồn và MP4 cuối, đối chiếu từng câu với
   hình; câu nào kể thêm việc không xuất hiện phải viết lại hoặc tách beat.

Cổng văn phong cứng: mỗi cue ≤ 240 ký tự, ≤ 2 câu, ≤ 4 mệnh đề (dấu phẩy/chấm
phẩy/hai chấm), ≤ 3 cụm cường điệu. Không kéo dài bằng sáo ngữ; muốn đủ thời lượng
thì thêm cue gắn với beat khác. Các mã lỗi văn phong `NARRATION_CUE_TOO_LONG`,
`NARRATION_TOO_MANY_SENTENCES`, `NARRATION_TOO_MANY_CLAUSES` và
`NARRATION_STYLE_OVERWRITTEN` đều là lỗi chặn.

Tổng duration WAV phải nằm trong 420–720 giây; ngoài khoảng này là
`REVIEW_DURATION_OUT_OF_RANGE` và phải sửa nội dung trước khi render bản đạt.

Sau khi audit MP4 đạt, không chạy `package`, không tạo ZIP, không gửi sang ChatGPT
Web và không dọn `run_dir`. Chỉ báo lại đường dẫn MP4, báo cáo kiểm định, duration,
số cue và các lỗi đã sửa để người dùng chuyển cho Codex khi cần.
