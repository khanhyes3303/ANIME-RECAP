# Thiết kế MVP hệ thống review anime

> Bản đặc tả này đã được mở rộng với mô hình `scene → shot → beat → voice cue →
> EDL`. Scene là đơn vị kể chuyện; shot chỉ là đơn vị cắt hình kỹ thuật.

## 1. Mục tiêu

Xây một dự án clean-room tối giản trong `D:\FINAL REVIEW ANIME` để Antigravity
Gemini 3.7 xử lý đúng một tập anime trong mỗi lần chạy.

Đầu vào duy nhất là một video anime dub tiếng Anh, thường dài khoảng 24 phút. Đầu ra
là một video review tiếng Việt dài từ 7 đến 12 phút, chỉ có giọng TTS tiếng Việt,
không chứa âm thanh nguồn hoặc nhạc nền.

Video review phải giữ nguyên cốt truyện, nhân vật, quan hệ, nguyên nhân và kết quả.
Phong cách kể là văn nói tự nhiên, hài, hợp khán giả Việt Nam năm 2026 và có thể dùng
từ thô tục khi hợp ngữ cảnh. Sự hài hước chỉ được thay đổi cách diễn đạt, không được
tạo thêm sự kiện hoặc nhét lời vào nhân vật.

## 2. Phạm vi MVP

MVP chỉ gồm sáu năng lực:

1. Chuẩn bị video và transcript tiếng Anh có timestamp.
2. Giao một tập cho Antigravity theo hợp đồng quan sát, viết và kiểm định.
3. Kiểm tra liên kết giữa từng mệnh đề narration và cảnh nguồn.
4. Tạo TTS bằng đúng provider và giọng đang dùng trong dự án V4 cũ.
5. Dựng video từ EDL với chuyển động nguồn 1:1 và chỉ một track TTS.
6. Đóng gói báo cáo, tạo ZIP bàn giao và dọn tài nguyên tạm an toàn.

MVP không có UI, dashboard, database, xử lý hàng loạt, tự đăng mạng xã hội, caption,
nhạc nền, video dọc, plugin, tìm dữ liệu anime trên web, tách nguồn âm thanh bằng AI,
CAS, hệ thống authority nhiều tầng hoặc các phase kiểu V4.

## 3. Nguyên tắc kiến trúc

- Dự án V4 cũ là nguồn tham khảo chỉ đọc. Dự án mới không phụ thuộc runtime vào thư
  mục cũ.
- Chỉ chuyển sang dự án mới những phần nhỏ đã được kiểm chứng và cần cho MVP.
- Một lần chạy chỉ được trỏ tới một anime, một mùa, một tập và một video nguồn.
- File nguồn không bao giờ bị sửa, di chuyển hoặc xóa.
- Mọi file tạm lớn phải nằm dưới `Tam_dang_xu_ly/<run_id>`.
- Không module nào được xóa đường dẫn ngoài thư mục tạm đã xác minh của chính run.
- Các file JSON là hợp đồng dữ liệu đơn giản, không tạo cây manifest hoặc lịch sử SHA.
- Lỗi phải dừng rõ ràng và tạo báo cáo; không được tự đổi điều kiện để báo `PASS`.

## 4. Cấu trúc thư mục người dùng

Tên thư mục dành cho người dùng sử dụng tiếng Việt không dấu để tránh lỗi công cụ:

```text
D:\FINAL REVIEW ANIME\
├── Kho_Anime\
│   └── <Ten_Anime>\
│       ├── Ho_so_bo_anime\
│       └── Mua_01\
│           └── Tap_001\
│               ├── Dau_vao\
│               ├── Su_that\
│               ├── Kich_ban\
│               ├── TTS\
│               ├── Ke_hoach_canh\
│               ├── Thanh_pham\
│               └── Bao_cao\
├── Tam_dang_xu_ly\
├── Bo_nao_Antigravity\
├── Goi_gui_ChatGPT_Web\
├── src\
├── tests\
└── run_episode.py
```

`Ho_so_bo_anime` lưu tên chuẩn, quan hệ nhân vật và tóm tắt ngắn các tập đã hoàn
thành. Một run được phép đọc hồ sơ này để giữ tính liên tục nhưng không được đọc hoặc
xử lý video của tập khác.

## 5. Lệnh vận hành

Điểm vào chính của MVP là một lệnh tạo job:

```powershell
python run_episode.py start --anime "Ten Anime" --season 1 --episode 1 --video "D:\video.mp4"
```

Người dùng giao đúng một job này cho Antigravity. Trong cùng một lần làm việc,
Antigravity chủ động gọi các bước nội bộ của `run_episode.py`, ghi artifact quan sát và
biên tập, chạy validator, TTS, render, audit và package. CLI không gọi Gemini qua API
và không cần một dịch vụ model riêng; Antigravity đang chạy chính là operator của job.

Lệnh `start` xác thực đầu vào, tạo thư mục tập/run và file hướng dẫn bước kế tiếp.
Các subcommand nội bộ chỉ phục vụ Antigravity và kiểm thử; người dùng không phải chạy
từng bước bằng tay. Không có lệnh batch trong MVP. Nếu thư mục tập đã có thành phẩm,
lệnh phải từ chối ghi đè; hỗ trợ revision mới nằm ngoài MVP.

## 6. Luồng xử lý một tập

Luồng trạng thái tuyến tính:

```text
CHUAN_BI
→ QUAN_SAT
→ VIET_KICH_BAN
→ KIEM_DINH_KICH_BAN
→ TAO_TTS
→ LAP_EDL
→ DUNG_VIDEO
→ KIEM_DINH_VIDEO
→ DONG_GOI
→ HOAN_THANH
```

Mọi lỗi nội dung đi vào `SUA_NOI_DUNG`; mọi lỗi ghép cảnh đi vào `SUA_EDL`. Tổng cộng
tối đa ba vòng sửa cho một tập. Hết ba vòng mà vẫn không đạt thì run kết thúc ở
`CAN_CON_NGUOI_XU_LY`, tạo ZIP báo cáo và không xuất nhãn thành phẩm đạt chuẩn.

## 7. Chuẩn bị video

Engine dùng FFprobe/FFmpeg để xác thực video, lấy duration, time base, độ phân giải và
trích audio phân tích. Whisper chạy local với ngôn ngữ cố định là tiếng Anh để tạo
transcript theo đoạn và theo từ khi khả dụng.

Video được chia thành shot và các cửa sổ tình huống có chồng lấn ngữ cảnh. Engine tạo
frame đại diện và clip kiểm tra tạm cho Antigravity. Opening, ending, credit và preview
tập sau được đánh dấu là ứng viên loại bỏ; Antigravity phải xác nhận theo hình ảnh vì
MVP không hard-code timestamp cho mọi anime. Cold open và post-credit có giá trị cốt
truyện phải được giữ.

## 8. Hợp đồng Antigravity

Antigravity là biên tập viên đa phương thức, còn engine giữ ràng buộc kỹ thuật. Một
agent run thực hiện ba vai trò tuần tự nhưng không trộn nhiệm vụ:

### 8.1. Quan sát viên

Xem clip/frame cùng transcript và tạo `su_that_tap_phim.json`. Mỗi sự kiện có ID,
timestamp nguồn, nhân vật, hành động, lời thoại liên quan, quan hệ nhân quả, mức quan
trọng và mức chắc chắn. Lượt này không viết joke hoặc narration.

### 8.2. Biên kịch

Chỉ dùng sổ sự thật đã tạo để chọn cốt truyện chính, thiết lập quan trọng cho phần sau,
cảnh hành động, phản ứng, fan-service và tình huống hài có giá trị. Kịch bản tiếng Việt
phải nằm trong ngân sách thời lượng 7–12 phút theo tốc độ thật của TTS. Mỗi cue chứa
text, các mệnh đề nguyên tử và danh sách ID sự kiện/cảnh hỗ trợ. Biên kịch phải làm
việc trên `ScenePacket`, không viết narration từ một danh sách shot rời rạc. Một scene
có thể dài 20–60 giây hoặc hơn và chứa nhiều shot; không có quy tắc cố định kiểu “mỗi
6 giây một câu”.

### 8.3. Kiểm định viên

Xem lại cảnh ứng với từng cue, rồi xem MP4 render cuối tại thời điểm cue được đọc.
Kiểm định viên chỉ ra lỗi theo loại và chủ sở hữu. Nó không được tự cho qua một câu chỉ
vì chính Antigravity đã viết câu đó.

Các file hướng dẫn trong `Bo_nao_Antigravity` phải cấm rõ việc suy diễn sự kiện, đổi
thứ tự nhân quả, gán sai người nói, dùng cảnh không liên quan hoặc hợp thức hóa lỗi bằng
điểm số cảm tính.

Job Antigravity cũng chứa `write_policy`: các thư mục artifact của đúng tập/run là
vùng được ghi; `Bo_nao_Antigravity`, `src`, `tests`, `docs`, Git metadata và video
nguồn là vùng chỉ đọc. Đây là ranh giới quyền hạn của operator. Nếu operator phát hiện
cần sửa một vùng chỉ đọc, nó phải tạo `BRAIN_CHANGE_REQUESTED` trong báo cáo và dừng,
không tự thay đổi bộ não hoặc validator.

## 9. Định nghĩa khớp lời và cảnh

Mỗi câu narration được tách thành mệnh đề nguyên tử. Một mệnh đề sự kiện chỉ đạt khi
cảnh gắn với nó thể hiện trực tiếp hành động, trạng thái hoặc phản ứng đang được kể,
hoặc transcript xác nhận lời thoại/sự kiện không thể hiện đầy đủ bằng một frame.

Chỉ số khớp 80% được tính bằng:

```text
tổng thời lượng cue có toàn bộ mệnh đề sự kiện được hỗ trợ trực tiếp
------------------------------------------------------------------- >= 0,80
                     tổng thời lượng narration
```

Ngưỡng 80% không cho phép 20% sai sự thật. Mâu thuẫn cốt truyện, sai nhân vật, sai quan
hệ, sai người nói hoặc bịa sự kiện có mức dung sai bằng 0. Phần không có hỗ trợ trực
tiếp chỉ được là cầu nối, nhận xét hoặc joke không tạo thêm sự kiện.

## 9.1. Scene packet, beat và khóa voice

`ScenePacket` là hợp đồng trung gian bắt buộc giữa quan sát và dựng video. Nó giữ ngữ
cảnh kể chuyện ở cấp scene, đồng thời bảo toàn thứ tự và ranh giới của các shot:

```text
ScenePacket
├── scene_id, source_start_ms, source_end_ms
├── story_purpose và event_ids
├── shots[] theo đúng thứ tự nguồn
│   ├── shot_id, source_start_ms, source_end_ms
│   ├── role: MUST_KEEP | OPTIONAL | TRANSITION
│   └── event_ids và lý do giữ/cắt
├── beats[] theo các mốc hành động hoặc phản ứng
│   ├── beat_id, source_start_ms, source_end_ms
│   ├── event_ids và shot_ids bắt buộc nhìn thấy
│   └── cue_ids liên quan
└── cue_ids và các ràng buộc dựng
```

Các quy tắc bắt buộc:

1. `MUST_KEEP` chứa hành động, kết quả, nhân vật hoặc thông tin nhân quả cần để hiểu
   scene. Không được cắt chỉ vì cue voice ngắn.
2. `OPTIONAL` và `TRANSITION` là vùng đầu tiên được phép cắt khi cần đạt 7–12 phút.
3. Một cue voice trong MVP thuộc về một scene và có thể phủ nhiều shot trong scene đó;
   không ép một shot phải có một câu thoại riêng. Khi chuyển sang scene khác thì tách
   cue hoặc tạo beat chuyển cảnh có liên kết rõ ràng.
4. Beat có mốc quan trọng phải được neo bằng khoảng thời gian nguồn. Câu voice mô tả
   beat chỉ được đặt trong cue có liên kết tới beat đó.
5. EDL phải tham chiếu ngược được `scene_id`, `shot_id`, `beat_id` và `event_ids`.
   Validator sẽ từ chối EDL chỉ đúng thời lượng nhưng không chứng minh được nó đang
   hiển thị scene nào.

Việc khớp thời lượng diễn ra sau khi tạo TTS thật:

```text
chọn scene + shot bắt buộc
→ viết cue/claim
→ tạo TTS và đo duration WAV thật
→ cắt shot tùy chọn hoặc sửa/chia cue
→ tạo EDL
→ render và kiểm tra lại tại thời điểm cue
```

Nếu TTS dài hơn phần hình hợp lệ, Antigravity phải rút gọn lời, chia cue hoặc bổ sung
shot liên quan trong cùng scene. Nếu TTS ngắn hơn tổng shot `MUST_KEEP`, nó phải chia
beat/cue hoặc rút ngắn narration; không được tăng tốc, đứng hình, lặp hình hay thêm
cảnh vô nghĩa. Sai số chỉ dành cho làm tròn frame/audio (mặc định ±40 ms mỗi cue),
không phải giấy phép chỉnh tốc độ.

“Khớp voice” ở đây là khớp ngữ nghĩa và mốc hành động với hình ảnh. Đây là narration
review tiếng Việt, không phải lồng tiếng thay cho nhân vật; mọi lời thoại nhân vật được
nhắc lại phải có transcript hoặc event làm bằng chứng. Audio dub tiếng Anh luôn bị tắt
ở đầu ra.

## 10. TTS

MVP giữ đúng hành vi đã dùng trong V4:

- `TikTokCapCutProvider`.
- Voice ID `BV074_streaming`.
- Biến môi trường `ANIME_RECAP_TIKTOK_SESSION`.
- Chunking có thể tái dựng nguyên văn narration.
- Retry có giới hạn, kiểm tra response và decode audio.
- Lưu MP3 provider và WAV PCM dùng cho phân tích/render.

Mặc dù script chạy trên máy và không tính phí, provider vẫn gọi endpoint TikTok. Khi
session thiếu hoặc hết hạn, run phải dừng với hướng dẫn rõ ràng; không tự đổi voice,
provider hoặc nội dung.

## 11. EDL và render

EDL là danh sách đoạn nguồn theo thứ tự cốt truyện, mỗi đoạn có source start/end,
program start/end, `scene_id`, `shot_id`, `beat_id`, `event_ids`, `cue_id` và vai trò
nội dung. Các đoạn của cùng cue phải giữ thứ tự nguồn, và tổng thời lượng hình hợp lệ
của cue phải khớp duration WAV thực tế trong sai số kỹ thuật cho phép. Renderer chỉ
được:

- trim cảnh đã chọn;
- ghép theo EDL;
- đặt TTS tiếng Việt;
- xuất video cùng chuyển động nguồn 1:1.

Renderer bị cấm speed-up, slow-down, freeze, loop, đảo hình, tái sử dụng cảnh ngoài
quyết định biên tập hoặc kéo cảnh bằng frame tĩnh. Audio của video nguồn không được
map vào đầu ra. MP4 cuối phải có đúng một audio stream bắt nguồn từ TTS.

## 12. Kiểm định và xử lý lỗi

Các hard gate trước khi đóng gói:

- Duration MP4 nằm trong 420–720 giây.
- Tỷ lệ khớp lời–cảnh đạt ít nhất 0,80.
- Không có mâu thuẫn sự thật mức dung sai 0.
- Mọi cue sự kiện có liên kết cảnh hợp lệ trong video nguồn.
- EDL nằm trong duration nguồn và không có đoạn thời lượng âm/rỗng.
- Video giữ chuyển động 1:1, không freeze/loop/time-stretch.
- MP4 không chứa audio nguồn, nhạc nền hoặc audio stream ngoài TTS.
- OP/ED/credit/preview không xuất hiện nếu không có quyết định giữ kèm lý do cốt truyện.
- Mỗi đoạn EDL truy ngược được về scene/shot/beat/event; không có cue “mồ côi” hoặc
  shot chính bị cắt mà không có quyết định biên tập hợp lệ.

Lỗi transcript hoặc quan sát thiếu bằng chứng quay lại `QUAN_SAT`. Lỗi narration hoặc
claim quay lại `VIET_KICH_BAN`. Lỗi scene/beat/shot hoặc nhịp quay lại `LAP_EDL`. Lỗi
TTS/render kỹ thuật được retry tại đúng bước. Antigravity tự chạy các vòng này trong
một agent run; người dùng không phải duyệt từng vòng. MVP giữ giới hạn tối đa ba vòng
sửa cho một tập để tránh lặp vô hạn, nhưng việc thiếu quota không phải lý do để hạ
tiêu chuẩn. Hết giới hạn mà chưa đạt thì kết thúc `CAN_CON_NGUOI_XU_LY`, tuyệt đối
không xuất PASS.

## 13. Đóng gói và dọn dẹp

Khi đạt, `Dau_vao/nguon.json` lưu đường dẫn tuyệt đối, hash và metadata của video
nguồn; video không bị sao chép vào tập. Tập lưu sổ sự thật, kịch bản, TTS cuối, EDL,
MP4 và báo cáo. ZIP gửi ChatGPT Web gồm báo cáo Markdown/JSON, kịch bản, EDL, lỗi và
lịch sử sửa, phiên bản công cụ, hash/path của video nguồn và hash/path MP4 cuối. ZIP
không chứa video nguồn hoặc MP4 lớn.

Khi hoàn thành, engine xóa proxy, frame, contact sheet, clip thử, audio phân tích và
render lỗi bên dưới `Tam_dang_xu_ly/<run_id>`. Khi thất bại, báo cáo và một tập bằng
chứng nhỏ được chuyển vào `Bao_cao`; các file tạm lớn vẫn được dọn. Mọi thao tác dọn
phải kiểm tra đường dẫn tuyệt đối nằm trong đúng thư mục run.

## 14. Kiểm thử MVP

MVP cần các test tự động tối thiểu:

- Unit test cho hợp đồng sổ sự thật, kịch bản, cue và EDL.
- Unit test scene packet: scene chứa nhiều shot, giữ thứ tự, bảo vệ `MUST_KEEP`, và
  EDL phải liên kết được scene/shot/beat/event.
- Unit test tính tỷ lệ khớp 80% và dung sai 0 cho mâu thuẫn sự thật.
- Unit test timing-fit: dùng duration WAV thật để sửa cue/cắt shot tùy chọn; từ chối
  speed-up, freeze, loop hoặc cắt mất shot bắt buộc.
- Unit test TTS bằng HTTP client giả; không gọi TikTok trong test mặc định.
- Unit test từ chối speed/freeze/loop và từ chối map audio nguồn.
- Unit test bảo vệ ranh giới dọn file tạm.
- Integration test FFmpeg trên fixture nhỏ để xác nhận duration, stream và mapping.
- Acceptance test một episode fixture nhỏ đi qua prepare → validate → TTS giả →
  render → package mà không cần Antigravity hoặc mạng thật.

Kiểm thử với một tập anime thật là bước nghiệm thu vận hành sau MVP, không được thay
thế các test xác định bằng lời đánh giá chủ quan của model.

## 15. Tiêu chí hoàn thành MVP

MVP hoàn thành khi người dùng có thể đặt một video dub tiếng Anh, chạy một lệnh cho
một tập, để Antigravity hoàn tất vòng quan sát/viết/kiểm định, rồi nhận được:

1. MP4 review tiếng Việt 7–12 phút chỉ có TTS.
2. Các artifact dễ đọc nằm đúng thư mục anime/mùa/tập.
3. Báo cáo PASS có bằng chứng hoặc báo cáo `CAN_CON_NGUOI_XU_LY` trung thực.
4. ZIP đủ cho ChatGPT Web đưa ra chỉ dẫn vòng tiếp theo.
5. Thư mục tạm của run đã được dọn mà không tác động tập khác hoặc video nguồn.
