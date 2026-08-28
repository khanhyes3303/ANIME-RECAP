# Prompt giao một tập cho Antigravity

Bạn hãy xử lý duy nhất tập anime trong job sau:

```text
<ĐƯỜNG_DẪN_RUN>\cong_viec_antigravity.json
```

Đọc `D:\FINAL REVIEW ANIME\Bo_nao_Antigravity\GEMINI.md` trước khi làm. Bạn là trợ
lý phân tích, không phải editor cuối.

Thực hiện liên tục trong một agent run:

```text
prepare nếu cần
→ mở thật video/frame và lập su_that_tap_phim.json
→ lập scene_packets.json có mô tả hình cụ thể
→ validate truth/scene
→ viết kich_ban_review.json bản nháp
→ validate/audit script
→ dừng tại CODEX_BIEN_TAP và báo cáo
```

Không được tạo hoặc sửa `khoa_cau_canh.json`, TTS, EDL, video candidate, thành phẩm,
review của Codex hay audit engine. Không chạy `lock`, `tts`, `render`, audit video,
đóng gói hoặc dọn run. Không tự cấp PASS cho video cuối.

Một cue nháp chỉ kể một hành động/phản ứng có bằng chứng; không sai người, đảo nhân
quả, bịa nội tâm hoặc nhét chữ vào mồm. Văn Việt tự nhiên, hài vừa đủ và không sáo
rỗng. Nếu cần thay đổi bộ não/mã nguồn, ghi `BRAIN_CHANGE_REQUESTED` và dừng.

Khi hoàn tất, báo đường dẫn run, job, truth, scene packet, script nháp, audit nháp và
những lỗi đã sửa để người dùng chuyển cho Codex.
