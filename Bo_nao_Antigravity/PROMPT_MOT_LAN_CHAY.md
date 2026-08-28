# Prompt một lần chạy Antigravity

Xử lý duy nhất tập anime trong job:

```text
<ĐƯỜNG_DẪN_RUN>\cong_viec_antigravity.json
```

Đọc toàn bộ `D:\FINAL REVIEW ANIME\Bo_nao_Antigravity\GEMINI.md`, sau đó tiếp tục từ
stage hiện tại đến `HOAN_THANH` trong một agent run. Bạn là operator thực hiện video;
không dừng để giao Codex biên tập.

Phải mở thật video/frame/clip, tạo atomic storyboard một hành động/phản ứng mỗi beat,
dùng producer và critic context khác nhau, tạo TTS đúng `BV074_streaming`, dựng proxy,
chỉ sửa beat lỗi, render final rồi chạy engine audit. Sau mỗi lệnh phải đọc
`next_action.json`. Không sửa bộ não, code, test, dependency, Git hoặc video nguồn.

Khi hoàn tất, báo đường dẫn `review_anime.mp4`, tổng thời gian, cache hit/miss, beat đã
sửa và lỗi đã loại. Nếu engine chặn sau ba vòng hoặc cần đổi kiến trúc, ghi
`BRAIN_CHANGE_REQUESTED` với bằng chứng và dừng trung thực.
