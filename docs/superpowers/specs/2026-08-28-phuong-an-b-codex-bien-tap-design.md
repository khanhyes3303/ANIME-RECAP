# Thiết kế phương án B: Codex biên tập và khóa lời với cảnh

## Mục tiêu

Sửa quy trình một tập để đầu ra là video review anime tiếng Việt dài 7–12 phút,
không dùng âm thanh nguồn, không sai cốt truyện và không đặt lời lên sai tình huống.
BLACK TORCH mùa 1 tập 1 là tập kiểm chứng đầu tiên; thiết kế phải dùng lại được cho
các anime khác mà không thay quy tắc cốt lõi.

Người dùng đã cho phép Codex trực tiếp viết lại lời review và tạo lại TTS khi bản nháp
của Antigravity không đạt hoặc không thể khóa đúng với hình.

## Nguyên nhân cần đổi kiến trúc

Quy trình hiện tại kiểm tra ID, thứ tự và tổng thời lượng nhưng không chứng minh rằng
nội dung nhìn thấy trong từng khoảng hình đúng với câu đang được đọc. Một cue có thể
chứa nhiều câu và phủ nhiều shot; EDL cắt shot theo thời lượng một cách cơ học. Báo
cáo PASS lại do chính Antigravity viết nên tạo vòng kiểm định khép kín.

Hiểu toàn bộ tập phim không đồng nghĩa với đặt đúng từng câu trên timeline thành phẩm.
Đơn vị khóa phải nhỏ hơn scene và cue: một câu kể nguyên tử gắn với đúng hành động
hoặc phản ứng nhìn thấy được.

## Phân vai

### Antigravity: trợ lý phân tích

- Quét toàn bộ video nguồn và transcript tiếng Anh.
- Đề xuất sự kiện, cảnh quan trọng, khoảng nguồn và lời nháp.
- Ghi mức chắc chắn và bằng chứng; không được tự cấp PASS cuối.
- Không sửa bộ não, mã nguồn, validator, test, tài liệu hoặc Git.

Đầu ra của Antigravity là dữ liệu tư vấn. Codex được quyền sửa, tách, loại bỏ hoặc
thay thế toàn bộ lời nháp và lựa chọn cảnh.

### Codex: biên tập viên chịu trách nhiệm cuối

- Xem bằng chứng hình của từng khoảng nguồn được chọn.
- Viết lại lời Việt tự nhiên, đúng sự kiện và đúng thứ tự nhân quả.
- Chia lời thành các `narration_span` nguyên tử.
- Chọn khoảng video nguồn chính xác cho từng span.
- Tạo lại TTS của span khi lời hoặc thời lượng chưa đạt.
- Kiểm tra video render tại đầu, giữa và cuối mỗi span; span không rõ ràng không được
  PASS tự động.

### Engine local: thực thi xác định

- Đo duration WAV thật, sinh EDL, cắt video bằng FFmpeg và loại toàn bộ audio nguồn.
- Chặn micro-clip do detector tạo ra; không dùng đoạn cực ngắn để lấp thời lượng.
- Không speed, freeze, loop hoặc kéo giãn hình để chữa lời dài.
- Chỉ ghi PASS kỹ thuật từ phép đo do engine tính, không đọc cờ PASS do agent tự khai.

### Người dùng

- Chuyển prompt và báo cáo giữa Codex với Antigravity khi cần.
- Chỉ cần xem MP4 cuối và phản hồi chất lượng.
- Không phải duyệt từng stage trung gian.

## Đơn vị khóa câu–cảnh

Mỗi `narration_span` có đúng một câu hoặc một ý nói liền mạch và các trường tối thiểu:

- `span_id`, `text`, `tts_path`, `tts_duration_ms`;
- `event_id`, nhân vật và hành động/phản ứng được kể;
- một hoặc vài khoảng nguồn liên tục, có `source_start_ms` và `source_end_ms`;
- ảnh neo đầu–giữa–cuối dùng để kiểm tra;
- kết quả kiểm định ngữ nghĩa và lý do nếu cần người xử lý.

Một span chỉ được kể 1–2 ý cùng xuất hiện trong cùng tình huống. Nếu hai hành động
độc lập xuất hiện ở hai thời điểm, phải tách thành hai span. Nếu TTS dài hơn hình hợp
lệ, thứ tự xử lý là rút lời, chia lời, tạo lại TTS hoặc chọn thêm shot liên quan trong
cùng tình huống. Không dùng hình vô nghĩa để đủ thời lượng.

Ranh giới shot chỉ là gợi ý cắt. Engine phải hợp nhất các shot liền nhau thành đoạn
biên tập có nghĩa; không đưa trực tiếp các mẩu 19–200 ms vào EDL. Ngưỡng chính xác sẽ
được khóa bằng test trong kế hoạch triển khai, ưu tiên không thấp hơn 500 ms trừ khi
Codex đánh dấu một chuyển động hành động bắt buộc.

## Kiểm định

### Cổng sự thật và văn phong

Một span thất bại nếu sai người, sai hành động, nói trước hình, nói sau hình, bịa động
cơ, thay đổi cốt truyện, dùng văn dịch máy/sáo rỗng hoặc đùa làm sai sự kiện. Câu phải
đọc tự nhiên bằng tiếng Việt và không kéo dài bằng tính từ hay meme.

### Cổng hình–lời

Sau render, engine trích ảnh tại đầu, giữa và cuối span trên chính MP4 thành phẩm.
Codex đối chiếu các ảnh đó với câu và khoảng nguồn. Các cảnh hành động, tiết lộ, nhân
quả và payoff chính phải khớp gần như tuyệt đối; tổng thời lượng được hình hỗ trợ trực
tiếp phải đạt ít nhất 80%.

### Cổng kỹ thuật

- Thành phẩm dài 420–720 giây.
- Chỉ có video và một luồng TTS tiếng Việt; không có audio tiếng Anh hoặc BGM.
- Chênh lệch đuôi audio/video không quá 80 ms.
- Không có span thiếu WAV, khoảng nguồn hoặc ảnh neo.
- Không có micro-clip dưới ngưỡng nếu không mang đánh dấu ngoại lệ được Codex duyệt.
- Antigravity không thể sửa trường PASS cuối.

## Luồng một tập

1. Engine chuẩn bị transcript, shot candidates và ảnh kiểm tra.
2. Antigravity quét nguồn, đề xuất sự thật, cảnh và lời nháp.
3. Codex kiểm tra, viết lại và tạo danh sách narration span cuối.
4. Local TTS tạo một WAV cho mỗi span; Codex sửa/tạo lại span không vừa hình.
5. Engine sinh EDL từ span đã khóa và render TTS-only.
6. Engine kiểm tra kỹ thuật; Codex kiểm tra ngữ nghĩa trên ảnh của MP4 cuối.
7. Lỗi quay lại đúng span, tối đa ba vòng. Chưa đạt thì báo trung thực, không xuất
   PASS giả.
8. Khi đạt, dừng và giao MP4 cùng báo cáo; không ZIP, không ChatGPT Web, không tự dọn
   tài nguyên.

## Đánh giá repo ngoài

Không nhập nguyên repo `AI-Movie-Shorts`. Có thể học ý tưởng mỗi clip có timestamp,
narration và audio riêng, nhưng loại bỏ ElevenLabs, BGM, UI, tải subtitle tự động,
vertical output và đặc biệt là time-stretch video.

Chỉ cân nhắc thêm PySceneDetect như dependency nhỏ cho ranh giới cảnh và ảnh
đầu–giữa–cuối. Nó không được quyết định ngữ nghĩa hoặc EDL cuối. Chưa thêm WhisperX:
word alignment hữu ích cho subtitle/audio nhưng không giải quyết câu tiếng Việt nằm
trên sai hình, đồng thời làm môi trường nặng hơn. Không thêm wrapper FFmpeg vì dự án
đã gọi FFmpeg trực tiếp và wrapper không tăng độ chính xác.

## Phạm vi triển khai đầu tiên

Chỉ sửa dữ liệu, validator, EDL, render/audit và hướng dẫn Antigravity cần thiết cho
khóa span. Không thêm UI, caption, BGM, batch, cloud TTS, đóng gói hay tự động dọn dẹp.
Sau khi test pipeline đạt, dựng lại BLACK TORCH mùa 1 tập 1 và dùng phản hồi MP4 cuối
của người dùng làm tiêu chuẩn nghiệm thu thực tế.
