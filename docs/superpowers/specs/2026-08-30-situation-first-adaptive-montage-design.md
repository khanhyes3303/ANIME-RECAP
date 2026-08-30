# Thiết kế biên tập review anime theo tình huống

## 1. Mục tiêu

Thay quy trình biên tập theo beat cơ học và kiểm định Gemini Web bằng một quy trình
local có thể dùng lại cho nhiều anime. Hệ thống phải hiểu nội dung từ transcript/SRT
và frame nguồn, chọn đúng thông tin đáng kể để kể lại, viết lời Việt tự nhiên rồi
khớp hình với TTS theo từng tình huống.

Đầu ra là video **kể lại cốt truyện**, không phải bản anime chỉ bị cắt ngắn. Trận
đánh, chuyển động đẹp hoặc một shot liên tục không tự động có giá trị review. Hình
chỉ được giữ khi nó minh họa thông tin, nguyên nhân, quyết định, bước ngoặt, cảm xúc
cần thiết hoặc kết quả đang được kể.

BLACK TORCH mùa 1 tập 1 là ca nghiệm thu đầu tiên. Quy tắc cốt lõi không được chứa
tên anime, số tập hoặc timestamp riêng của ca này.

## 2. Các nguyên tắc bất biến

1. Không đặt trước thời lượng lấy, thời lượng bỏ hoặc tỷ lệ lấy/bỏ.
2. Transcript/SRT và frame là hai nguồn bằng chứng chính để xác định tình huống.
3. Mỗi tình huống được phân tích thành thông tin chính, thông tin phụ, hành động
   chính, hành động phụ, nguyên nhân, bước ngoặt và kết quả.
4. Thông tin cốt truyện quan trọng hơn việc giữ trọn vũ đạo hoặc tính liên tục của
   một trận đánh.
5. Sau mỗi khoảng nguồn được giữ phải có một khoảng nguồn bị bỏ thật sự. Giữa hai
   khoảng được giữ, gap nguồn chứng minh phần bỏ; với khoảng giữ cuối video review,
   phần nguồn còn lại sau điểm kết thúc là khoảng bỏ. Engine không được ghép hai
   khoảng liền kề rồi khai rằng đã thực hiện nhịp lấy/bỏ.
6. Khoảng bỏ không được tạo giả bằng micro-gap hoặc bằng cách để lại micro-clip rác.
   Ngưỡng kỹ thuật mặc định là 500 ms và phải cấu hình được; đây chỉ là ngưỡng chống
   gian lận/mảnh rác, không phải nhịp dựng cố định.
7. Điểm cắt bám ranh giới shot hợp lệ. Frame đen, flash, logo, chuyển cảnh và mẩu hình
   cực ngắn không được lọt vào đầu hoặc cuối clip.
8. Opening, ending, recap, credit, quảng cáo và preview bị loại. Cold open hoặc
   post-credit chỉ được giữ nếu chứa diễn biến cốt truyện cần kể.
9. Xử lý tuần tự từng tình huống: chọn hình, viết lời, tạo TTS, khớp thời lượng và
   kiểm định xong tình huống hiện tại trước khi chuyển sang tình huống kế tiếp.
10. Gemini Web không phải dependency và không nằm trong đường chạy mặc định.

## 3. Kiến trúc và trách nhiệm

Thiết kế không giả định rằng mã số học có thể tự hiểu cốt truyện. Nó tách phần suy
luận biên tập khỏi phần thực thi xác định:

1. **Evidence extractor local** tạo transcript/SRT, shot boundaries, frame đại diện,
   OCR và metadata chuyển động. Thành phần này không quyết định nội dung đáng kể.
2. **Situation editor agent** đọc gói transcript + frame và tạo Situation, phân cấp
   chính/phụ, thông tin cần kể và evidence ranges. Agent này chạy trong phiên làm việc
   local của Codex hoặc Antigravity; không điều khiển Gemini Web và không tự cấp PASS.
3. **Narration editor agent** viết lời Việt cho từng tình huống đã khóa bằng chứng,
   giữ context trước/sau và xuất NarrationUnit có cấu trúc.
4. **Deterministic engine** kiểm schema/range/gap, tạo TTS, dựng EDL, render, đo duration,
   fingerprint artifact và quyết định các cổng kỹ thuật.
5. **Local semantic audit** đối chiếu narration claim với transcript refs và frame neo.
   Kết quả thất bại quay lại đúng situation/unit, không quay lại toàn tập.

Agent có quyền đề xuất và sửa nội dung trong artifact của run. Chỉ engine được chuyển
stage hoặc ghi kết quả validator. Không agent nào được sửa mã nguồn, test, policy hoặc
run state để hợp thức hóa output.

## 4. Đơn vị dữ liệu

### 4.1. Situation

`Situation` là đơn vị hiểu và kể chuyện, không phải một khoảng thời gian cố định:

- `situation_id`, `source_start_ms`, `source_end_ms`;
- nhân vật, địa điểm và trạng thái mở đầu;
- `main_plot` hoặc `supporting_plot`;
- nguyên nhân, hành động, quyết định, bước ngoặt và kết quả;
- transcript/SRT refs và frame/shot refs;
- thông tin mới mà người xem cần biết;
- liên kết với tình huống trước và sau;
- mức chắc chắn và lý do chọn hoặc bỏ.

Một tình huống có thể kéo dài vài giây hoặc nhiều phút. Thay đổi chủ đề, mục tiêu,
địa điểm, nhóm nhân vật, quan hệ nhân quả hoặc kết quả tạo ranh giới tình huống mới.
Shot chỉ là dữ liệu kỹ thuật giúp chọn hình bên trong tình huống.

### 4.2. Evidence range

Mỗi khoảng hình được giữ có:

- khoảng nguồn và danh sách shot;
- thông tin hoặc diễn biến mà nó minh họa;
- transcript refs khi có lời thoại liên quan;
- frame neo đầu, giữa và cuối;
- lý do đoạn này đáng giữ;
- khoảng nguồn bị bỏ trước khoảng giữ kế tiếp.

Không có `evidence range` chỉ vì hình đẹp. Nếu trận đánh không cung cấp thông tin
mới, chỉ giữ hình đại diện ngắn cho việc giao chiến hoặc bỏ toàn bộ và kể kết quả.

### 4.3. Narration unit

Mỗi `NarrationUnit` thuộc đúng một tình huống và gồm:

- nội dung sự thật cần truyền đạt;
- lời review tiếng Việt;
- evidence ranges hỗ trợ;
- câu nối từ tình huống trước và câu dẫn sang tình huống sau;
- WAV TTS và thời lượng đo thật;
- EDL cục bộ đã khớp với TTS;
- trạng thái kiểm định và fingerprint của artifact.

## 5. Luồng phân tích

### 5.1. Chuẩn bị

Engine tạo transcript/SRT có timestamp, shot boundaries và frame đại diện. Frame
được lấy tại ranh giới shot và các điểm có thay đổi hình/chuyển động đáng kể; không
chỉ lấy mẫu thưa theo một chu kỳ cố định vì có thể bỏ sót hành động hoặc biểu cảm.

Nếu thiếu executable hoặc dependency bắt buộc, preflight phải dừng trước khi xử lý,
nêu chính xác tên công cụ và cách người dùng cài. Hệ thống không tự cài công cụ.

### 5.2. Nhận diện vùng cấm

Vùng cấm được nhận diện từ tổ hợp transcript, OCR/frame và mẫu hình:

- nhạc/credit và chuỗi hình mang tính opening hoặc ending;
- recap kể lại nội dung đã xảy ra trước tập hiện tại;
- title card không mang thông tin cần kể;
- quảng cáo, preview và credit.

Kết quả là danh sách source ranges có lý do và độ tin cậy. Validator chặn mọi EDL
tham chiếu vùng đã xác nhận cấm.

### 5.3. Chia tình huống

Engine hợp nhất transcript và frame theo timeline, sau đó tạo candidate situations.
Mỗi candidate phải trả lời được: ai đang làm gì, vì sao, điều gì mới xuất hiện và kết
quả có ảnh hưởng gì. Những cửa sổ không trả lời được phải được gộp thêm ngữ cảnh hoặc
đánh dấu không chắc chắn; không được tự bịa nội dung để lấp chỗ trống.

### 5.4. Phân cấp nội dung

Mỗi thành phần được chấm theo giá trị kể chuyện:

- tiết lộ thông tin mới;
- nguyên nhân hoặc hệ quả;
- quyết định của nhân vật;
- nhân vật/năng lực/xung đột mới;
- bước ngoặt hoặc kết quả;
- cảm xúc cần thiết để hiểu hành vi tiếp theo.

Điểm bị trừ cho lời thoại lặp, chuyển động lặp, đứng chờ, lia máy, phản ứng không thêm
nghĩa và chuỗi đánh nhau không làm thay đổi trạng thái câu chuyện.

Quy tắc chọn:

- tình huống chính và diễn biến chính: kể đủ thông tin cần hiểu;
- tình huống chính nhưng hành động phụ: rút gọn thành hình minh họa;
- tình huống phụ có thiết lập/payoff về sau: giữ thông tin liên quan;
- tình huống phụ không ảnh hưởng mạch kể: bỏ;
- hành động không chứa thông tin đáng review: bỏ, bất kể độ dài hoặc độ đẹp.

## 6. Bộ chọn hình lấy/bỏ thích ứng

Bộ chọn làm việc bên trong một tình huống, không dùng công thức giây cố định:

1. Xác định chuỗi thông tin cần kể theo thứ tự.
2. Với mỗi thông tin, chọn một hoặc nhiều khoảng hình đại diện tốt nhất.
3. Giữa hai khoảng được chọn, bắt buộc có một source gap bị bỏ và gap đó phải đạt
   ngưỡng kỹ thuật chống micro-gap.
4. Nếu hai thông tin quan trọng nằm liền nhau, bộ chọn phải tìm điểm lược hợp lý trong
   hành động, phản ứng, hold hoặc shot phụ lân cận. Nó không được giữ liền toàn bộ chỉ
   để bảo toàn choreography.
5. Nếu không thể tạo khoảng bỏ mà vẫn chứng minh được hai thông tin độc lập, hệ thống
   gộp chúng thành một evidence range cho một narration unit, rồi phải bỏ phần nguồn
   tiếp theo trước evidence range kế tiếp.
6. Mọi mảnh nguồn còn lại dưới ngưỡng clip tối thiểu bị hấp thụ vào khoảng giữ hợp lệ
   hoặc bỏ hoàn toàn; không được đưa vào EDL như frame rác.

Như vậy “có lấy phải có bỏ” là ràng buộc đo được trên toàn timeline, nhưng thời lượng
lấy và bỏ vẫn do nội dung quyết định.

## 7. Viết kịch bản và văn phong

Kịch bản được viết sau khi khóa thông tin và evidence ranges của từng tình huống.
Không viết một kịch bản toàn tập trước rồi ép hình vào lời.

Văn phong bắt buộc:

- tiếng Việt nói tự nhiên, dân dã, gọn và dễ nghe;
- được dùng từ thô tục khi hợp tình huống và đúng giọng kể đã chọn;
- không chửi dày đặc, không cố nhét meme và không dùng tục ngữ vô nghĩa để kéo dài;
- không dịch sát cấu trúc câu tiếng Anh;
- không bịa lời thoại, động cơ, quan hệ hoặc sự kiện;
- gọi nhân vật nhất quán;
- câu cuối tình huống trước phải dẫn tự nhiên tới câu đầu tình huống sau.

Mỗi narration unit chỉ kể thông tin đã có bằng chứng. Joke hoặc nhận xét được phép nếu
không biến thành một sự kiện giả và không che mất diễn biến chính.

## 8. TTS và khóa hình–voice

Sau khi viết xong một narration unit:

1. Tạo WAV TTS và đo duration thật.
2. Xây EDL cục bộ từ các evidence ranges đã chọn.
3. Điều chỉnh nhẹ tốc độ video để khớp voice; dải mặc định là 0,80x–1,30x và cấu hình
   được. Không đổi tốc độ/pitch TTS để chữa kịch bản dài.
4. Nếu vẫn không khớp, lần lượt: rút lời dư, viết lại câu, chọn thêm bằng chứng có giá
   trị trong cùng tình huống hoặc tách narration unit.
5. Kiểm tra frame đầu–giữa–cuối trên bản render cục bộ và khóa unit đạt chuẩn.

Sau khi khóa một tình huống, tình huống sau nhận phần tóm tắt cuối của tình huống trước
làm context. Một lượt audit toàn tập chỉ được mở lại unit đã khóa khi phát hiện mâu
thuẫn sự thật, lặp ý hoặc câu nối hỏng; không được làm lại vô hạn vì sở thích câu chữ.

## 9. Validator local

Validator phải tự tính, không tin cờ PASS do agent ghi:

- mọi narration claim có transcript hoặc frame/event evidence;
- mọi evidence range nằm trong đúng situation và ngoài vùng cấm;
- source ranges tăng dần, không chồng lấn;
- sau mỗi range được giữ có omitted gap hợp lệ, bao gồm phần source tail sau range
  cuối;
- không có micro-clip, frame rác hoặc micro-gap giả;
- TTS duration và EDL duration khớp trong sai số kỹ thuật;
- tốc độ clip nằm trong policy;
- chỉ có một track TTS tiếng Việt, không có audio nguồn;
- câu nối không lặp thông tin hoặc tạo mâu thuẫn với tình huống trước/sau;
- artifact fingerprint thay đổi trước khi cho phép chạy lại một vòng sửa.

Nếu hai vòng sửa liên tiếp có cùng fingerprint hoặc cùng lỗi mà không có artifact nội
dung thay đổi, run dừng ở `CAN_CON_NGUOI_XU_LY` với lỗi `KHONG_CO_TIEN_TRIEN`. Không
render, TTS hoặc gửi kiểm định lặp lại trên cùng dữ liệu.

## 10. Vai trò của Gemini Web

Gemini Web bị loại khỏi đường chạy mặc định. Thành công của pipeline không phụ thuộc
Chrome, cửa sổ foreground, phiên đăng nhập, selector UI hoặc phản hồi từ Gemini.

Một lệnh audit Gemini riêng có thể tồn tại về sau như kiểm tra tùy chọn do người dùng
chủ động yêu cầu. Kết quả của nó không được tự động tạo vòng sửa và không được ghi đè
kết quả validator local.

## 11. Ca BLACK TORCH tập 1

Lần dựng lại hiện tại phải áp dụng cùng engine tổng quát với policy của tập:

- bỏ toàn bộ phần tuổi thơ, logo và title card;
- program bắt đầu tại shot băng nhóm bên bờ sông, source khoảng 148482 ms;
- không cho phép bất kỳ source range nào trước mốc này vào EDL;
- kể từ tình huống bờ sông trở đi theo quy tắc thông tin cốt truyện trước, hành động
  chỉ là hình minh họa;
- không xuất final cho tới khi proxy vượt toàn bộ validator local.

Timestamp trên là policy đầu vào của ca nghiệm thu, không được hard-code vào engine.

## 12. Kiểm thử và tiêu chí nghiệm thu

### Kiểm thử tự động

- chia situation từ transcript và shot/frame fixture;
- loại opening/ending/recap/title/credit;
- phân cấp tình huống chính/phụ và hành động có/không có giá trị kể chuyện;
- bảo đảm mọi cặp kept ranges có omitted gap hợp lệ;
- chặn micro-clip, micro-gap, vùng cấm và tốc độ ngoài policy;
- kiểm tra TTS/EDL duration;
- kiểm tra fingerprint và dừng no-progress sau hai vòng;
- xác nhận đường chạy mặc định không cần module Gemini/Chrome.

### Nghiệm thu nội dung

Với BLACK TORCH tập 1:

- frame đầu là băng nhóm bên bờ sông, không phải manga, tuổi thơ hoặc title card;
- không còn hình thuộc vùng source trước 148482 ms;
- mỗi tình huống kể đúng thông tin mới và bỏ phần hành động/lời thoại dư;
- giữa các clip được giữ luôn có phần nguồn bị lược;
- voice Việt tự nhiên, dân dã, có độ thô tục hợp ngữ cảnh nhưng không gượng ép;
- lời và hình khớp tại đầu, giữa, cuối mỗi narration unit;
- video chỉ chứa TTS tiếng Việt và đạt thời lượng mục tiêu hiện hành của dự án.

Sau khi ca này đạt, chạy một fixture hội thoại nhiều và một fixture hành động ít lời.
Hai fixture phải dùng cùng policy engine; chỉ dữ liệu phân tích và cấu hình thay đổi.

## 13. Phạm vi triển khai

Bao gồm: data model tình huống/evidence/narration, bộ chọn adaptive keep/skip,
validator local, luồng script–TTS–EDL tuần tự, progress fingerprint, cập nhật CLI và
hướng dẫn operator, test tự động và dựng lại BLACK TORCH tập 1.

Không bao gồm: UI mới, batch nhiều tập, đăng video, caption, nhạc nền, tự cài dependency,
plugin Antigravity hoặc thay đổi video nguồn. Batch chỉ được làm sau khi một tập hội
thoại và một tập hành động vượt cùng bộ nghiệm thu.
