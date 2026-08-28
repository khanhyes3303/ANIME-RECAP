# Thiết kế Antigravity-first với beat hình–lời nguyên tử

## Mục tiêu

Một lần người dùng giao đúng một tập anime dub tiếng Anh, Antigravity phải tự hoàn
thành video review tiếng Việt dài 7–12 phút. Video cuối chỉ có TTS tiếng Việt
`BV074_streaming`, không có audio nguồn, không sửa cốt truyện và không đặt lời lên
sai tình huống. Codex chỉ thiết kế, khóa và sửa bộ não/quy trình sau khi nhận phản
hồi; Codex không trực tiếp viết lại từng câu, ghép cảnh, tạo TTS hay render tập phim.

Thiết kế phải giảm thời gian làm lại: sửa một beat không được tạo lại TTS và clip của
các beat không đổi. BLACK TORCH mùa 1 tập 1 là bài kiểm thử hồi quy đầu tiên, nhưng
không chứa quy tắc đặc thù cho bộ phim này.

## Quyết định kiến trúc

Ba hướng đã được cân nhắc:

1. Tăng số frame toàn tập và giữ quy trình hiện tại. Hướng này tăng chi phí nhưng vẫn
   để một cue dài chứa nhiều hành động và vẫn không chứng minh đồng bộ cục bộ.
2. Để Codex tiếp quản biên tập cuối. Hướng này đã cho video tạm ổn nhưng chậm, hao
   quota Codex và trái với mục tiêu một lần chạy Antigravity.
3. Cho Antigravity sở hữu toàn bộ vòng đời một tập, nhưng bắt buộc làm qua beat
   nguyên tử, cổng máy móc, critic độc lập và cache gia tăng.

Chọn hướng 3. Không thêm MCP, UI, BGM, caption, batch nhiều tập hoặc nhập nguyên repo
ngoài trong lần triển khai này. Shot detector và transcript hiện có tiếp tục là dữ
liệu gợi ý; FFmpeg và engine local là nơi đo thời gian và render xác định.

## Phân quyền bất biến

### Codex

- Sở hữu `Bo_nao_Antigravity`, `src`, `tests`, `docs`, cấu hình và Git.
- Thiết kế schema, stage, validator, cổng nghiệm thu và prompt một lần chạy.
- Chỉ xem báo cáo lỗi hoặc phản hồi video để sửa bộ não trong những lượt sau.
- Không tham gia biên tập từng tập trong luồng bình thường.

### Antigravity

- Đọc video nguồn, transcript, shot map, frame/clip bằng chứng và job một tập.
- Tạo sự thật, storyboard beat nguyên tử, lời review, semantic review và báo cáo.
- Gọi CLI local để tạo TTS, EDL, proxy, kiểm định và render cuối.
- Tự sửa tối đa ba vòng, chỉ sửa các beat bị lỗi.
- Không sửa bộ não, mã nguồn, test, tài liệu, cấu hình, Git hoặc video nguồn.
- Nếu cần đổi luật hoặc code, ghi `BRAIN_CHANGE_REQUESTED` rồi dừng.

### Engine local

- Tạo artifact xác định từ input: shot/frame index, TTS, EDL, proxy, anchor, thống kê
  cache, kiểm tra stream và render cuối.
- Không tin trường `passed` do agent nhập. Engine tự tính kết quả từ các finding, dữ
  liệu thời gian, hash và bằng chứng bắt buộc.
- Kiểm tra hash bộ não/job để phát hiện Antigravity sửa phạm vi chỉ đọc.

### Người dùng

- Dán một prompt cho Antigravity và xem MP4 cuối.
- Chuyển báo cáo cho Codex khi run bị chặn hoặc video thực tế chưa đạt.
- Không phải duyệt từng stage trung gian.

## Đơn vị dữ liệu: atomic beat

`atomic_storyboard.json` là nguồn sự thật biên tập của một tập. Mỗi beat chứa đúng
một hành động chính, một phản ứng chính hoặc một ý bối cảnh không phụ thuộc thời điểm.
Một beat có thể dùng nhiều shot liên tiếp trong cùng tình huống; shot không phải là
đơn vị lời thoại.

Mỗi beat có tối thiểu:

- `beat_id`, `scene_id`, `event_ids`, `claim_ids`;
- `source_ranges` với `source_start_ms`, `source_end_ms` và `shot_ids`;
- `visual_fact`: mô tả trung tính điều thật sự nhìn thấy;
- `characters_visible` và `characters_spoken_about`;
- `sync_mode`: `ACTION`, `REACTION` hoặc `CONTEXT`;
- `action_window_start_ms`, `action_window_end_ms` đối với `ACTION`/`REACTION`;
- `narration_text`: một câu hoặc một ý nói liền mạch;
- `frame_evidence`: frame đầu/cuối mỗi range và frame tại action window;
- `estimated_tts_ms`, sau tổng hợp có thêm `actual_tts_ms` và `tts_cache_key`;
- `status`: `DRAFT`, `NEEDS_REPAIR`, `LOCKED` hoặc `REJECTED`;
- danh sách `finding_codes` do critic tạo, không có trường `passed` do producer tự đặt.

Luật bắt buộc:

- Hai hành động xảy ra ở hai thời điểm khác nhau phải là hai beat.
- Lời được viết sau khi đã khóa visual fact và source range; không viết lời trước rồi
  tìm cảnh lấp vào.
- Lời dài hơn hình hợp lệ phải được rút hoặc tách beat. Không speed, freeze, loop hay
  lấy cảnh kế tiếp sai nghĩa để đủ thời lượng.
- Cảnh hành động/phản ứng phải bắt đầu gần điểm lời tương ứng; dung sai mục tiêu là
  500 ms. Beat `CONTEXT` được phép dung sai 1.000 ms nhưng vẫn phải cùng tình huống.
- Một đoạn TTS 6 giây không bắt buộc dùng một shot 6 giây; nó có thể dùng nhiều shot
  có cùng ý nghĩa với câu đang đọc.
- OP, ED, credits, next preview và cảnh lấp thời lượng không được đi vào storyboard.

## Bằng chứng hình ảnh có mục tiêu

Không trích thêm frame đồng đều trên toàn tập. Engine dùng shot map hiện có để tạo:

- frame đầu, giữa và cuối mỗi shot được chọn;
- frame ngay trước/sau ranh giới shot;
- frame tại action window do Antigravity khai báo;
- với cảnh chuyển động nhanh, một gói dày 0,25–0,5 giây/frame quanh action window.

Mọi frame có timestamp mili giây và liên kết ngược đến `beat_id`, `range_id`,
`shot_id`. Antigravity phải mở frame/clip thật; transcript hoặc tên shot không được
coi là bằng chứng thị giác.

Transcript dub tiếng Anh chỉ hỗ trợ xác định lời nói, tên và nhân quả. Nó không được
dùng một mình để chọn hình. Chưa thêm WhisperX trong phạm vi đầu tiên; chỉ cân nhắc
sau nếu timestamp transcript hiện tại được đo bằng bài kiểm thử và chứng minh là
nguyên nhân lỗi.

## Luồng một lần chạy Antigravity

1. `prepare`: xác minh source, tạo/reuse transcript, shot map và frame index.
2. `observe`: Antigravity xem toàn tập, ghi sự thật và vùng loại bỏ.
3. `storyboard`: chọn cảnh và tạo atomic beat có visual fact, action window, evidence.
4. `write`: viết tiếng Việt theo từng beat từ sự thật đã khóa.
5. `critic-script`: chạy một lượt critic tách biệt với lượt producer; kiểm tra sự thật,
   độ tự nhiên, lặp công thức và khả năng nói vừa khung hình.
6. `tts`: chỉ tổng hợp beat `LOCKED`; reuse audio nếu cache key không đổi.
7. `fit`: đo WAV thật. Beat không vừa hình quay về `NEEDS_REPAIR`, chỉ beat đó được
   rút/tách và tạo lại TTS.
8. `proxy`: dựng 360p từ các beat đã khóa, không ghi đè thành phẩm.
9. `critic-video`: critic mở proxy cùng anchor/action-window, ghi finding theo beat.
10. `repair`: sửa tối đa ba vòng, chỉ invalidating cache của beat thay đổi.
11. `final-render`: chạy đúng một lần khi không còn finding chặn.
12. `engine-audit`: engine tự đo stream, duration, drift, coverage và hash; khi đạt thì
    xuất `review_anime.mp4`, báo cáo và dừng.

Đây vẫn là một prompt và một agent run đối với người dùng. Các vòng bên trong không
yêu cầu người dùng hoặc Codex can thiệp.

## Cổng sự thật và văn phong

Producer không được tự duyệt sản phẩm của mình. `critic-script` phải đọc lại evidence
và sinh finding cho từng beat. Finding chặn gồm ít nhất:

- `FACT_CONTRADICTION`, `WRONG_CHARACTER`, `INVENTED_MOTIVE`;
- `ACTION_MISMATCH`, `SCENE_MISMATCH`, `VOICE_AHEAD`, `VOICE_BEHIND`;
- `MULTI_ACTION_BEAT`, `LOW_VALUE_FOOTAGE`, `MISSING_MAIN_PLOT`;
- `FORMULAIC_PROSE`, `REPEATED_OPENING`, `TRANSLATIONESE`, `FORCED_JOKE`;
- `TTS_TOO_LONG`, `TTS_TOO_SHORT`, `MISSING_EVIDENCE`.

Validator văn phong máy móc phải bổ sung kiểm tra toàn tập, không chỉ từng câu:

- lặp cụm mở đầu/kết câu và lặp n-gram;
- chuỗi câu có cùng cấu trúc;
- mật độ từ nối công thức như “lúc này”, “ngay sau đó”, “không ngờ rằng”;
- câu quá dài, quá nhiều mệnh đề, lặp tính từ hoặc meme;
- joke không có sự thật tương ứng.

Validator không tự khẳng định câu “hay”. Critic phải sửa cho đến khi câu đọc thành
tiếng Việt nói tự nhiên, đúng nhân vật và đúng tình huống. Câu đùa chỉ thay cách kể,
không thay sự kiện.

## Cổng hình–lời và video

Engine chỉ cho phép render cuối khi:

- mọi beat có source range, shot, visual fact, evidence và WAV;
- tổng source duration của beat khớp actual TTS trong dung sai 80 ms;
- action window nằm trong footage của beat;
- không có finding chặn và không còn beat `NEEDS_REPAIR`;
- coverage trực tiếp đạt tối thiểu 90% theo thời lượng TTS;
- video dài 420–720 giây, một video stream và một audio stream TTS;
- drift audio/video không quá 80 ms;
- không có audio dub tiếng Anh, BGM, speed, freeze hoặc loop;
- hash bộ não và policy không thay đổi trong run.

Coverage không được tính bằng một boolean `supported` do Antigravity tự ghi. Mỗi beat
phải có evidence hợp lệ và không có finding chặn; engine cộng actual TTS duration của
những beat thỏa toàn bộ điều kiện.

## Cache và giới hạn thời gian

Các cache được lưu theo tập và không phụ thuộc run tạm:

- `source_analysis_cache`: source hash → transcript, shot map, frame index;
- `tts_cache`: hash của normalized text + provider + voice + policy → MP3/WAV/duration;
- `clip_cache`: source hash + source ranges + render policy → proxy clip;
- `qa_cache`: beat content hash + evidence hash + proxy hash → critic findings.

Sửa một beat chỉ xóa cache TTS/clip/QA của beat đó. `narration.wav`, EDL và proxy được
nối lại từ các thành phần còn hợp lệ. Run ghi số cache hit/miss, thời gian từng stage,
số beat sửa và lý do sửa để Codex tìm đúng điểm nghẽn từ báo cáo ngắn.

Mục tiêu vận hành, không phải lời hứa cứng, là lần chạy đầu hoàn thành trong khoảng
30–60 phút trên máy hiện tại; sửa nhỏ phải nhanh hơn đáng kể và không tổng hợp lại
toàn bộ TTS.

## Stage và artifact mới

Stage `CODEX_BIEN_TAP` bị loại khỏi đường chạy bình thường. Luồng mới có các stage:

`CHUAN_BI → QUAN_SAT → LAP_STORYBOARD → VIET_LOI → PHAN_BIEN_KICH_BAN → TAO_TTS →
CAN_TTS → DUNG_PROXY → PHAN_BIEN_VIDEO → SUA_BEAT | DUNG_VIDEO_CUOI → KIEM_DINH_ENGINE
→ HOAN_THANH`.

Artifact chính:

- `Su_that/su_that_tap_phim.json`;
- `Su_that/scene_packets.json`;
- `Kich_ban/atomic_storyboard.json`;
- `Kich_ban/critic_script.json`;
- `TTS/atomic_tts_manifest.json`;
- `Ke_hoach_canh/atomic_edl.json`;
- run-local `proxy/review_proxy.mp4`;
- `Bao_cao/critic_video.json` và `Bao_cao/kiem_dinh_engine.json`;
- `Thanh_pham/review_anime.mp4`.

Tên thư mục theo anime/mùa/tập hiện tại được giữ nguyên. File tạm trong run được dọn
sau khi hoàn thành, nhưng cache dùng lại và báo cáo cuối của tập phải được giữ.

## Repo và dependency ngoài

- Không nhập nguyên `AI-Movie-Shorts`; chỉ giữ ý tưởng clip có timestamp/audio riêng
  và dọn file tạm. Không dùng ElevenLabs, BGM, UI, tải subtitle hay time-stretch.
- Không thêm MCP vì nó không cải thiện ràng buộc hình–lời.
- Không thêm repo mới trong lần triển khai đầu tiên.
- Chỉ thêm PySceneDetect nếu kiểm tra môi trường cho thấy shot map hiện tại không được
  tạo bằng detector ổn định. Nếu shot map đã đủ, không thay dependency.
- WhisperX là nâng cấp có điều kiện sau benchmark, không phải yêu cầu của kiến trúc.

## Kiểm thử và nghiệm thu

Triển khai theo TDD với unit test cho schema, stage, quyền ghi, cache, validator,
coverage và invalidation từng beat; integration test cho TTS/EDL/proxy gia tăng;
acceptance test cho một prompt Antigravity đi từ job đến MP4 mà không có stage Codex.

BLACK TORCH mùa 1 tập 1 được chạy lại sau khi toàn bộ test tự động đạt. Thành công kỹ
thuật không đồng nghĩa chất lượng nội dung tuyệt đối: người dùng xem MP4 cuối và phản
hồi. Nếu còn lỗi, Codex sửa bộ não hoặc validator từ bằng chứng trong báo cáo; Codex
không vá thủ công riêng tập phim.

## Ngoài phạm vi

Không làm UI, caption, BGM, Shorts/vertical, batch nhiều tập, cloud TTS, auto-upload,
đóng gói ZIP, ChatGPT Web hoặc plugin mới. Không tối ưu phong cách cho riêng BLACK
TORCH và không cho Antigravity tự sửa kiến trúc.
