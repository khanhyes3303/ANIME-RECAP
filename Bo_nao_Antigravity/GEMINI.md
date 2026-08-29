# Bộ não Antigravity — operator review một tập

Bạn xử lý đúng một tập anime dub tiếng Anh trong `cong_viec_antigravity.json` và tự
tạo video review tiếng Việt hoàn chỉnh trong một agent run. Codex chỉ sở hữu kiến
trúc; không chờ Codex biên tập tập.

## Quyền hạn bất biến

Bạn được đọc video nguồn, transcript, shot/frame, job và artifact của tập. Bạn được
ghi các output trong `required_outputs` và gọi `run_episode.py` để tạo TTS, EDL,
proxy, final candidate và audit.

Bạn không được sửa `Bo_nao_Antigravity`, `src`, `tests`, `docs`, `pyproject.toml`,
`uv.lock`, `.git`, video nguồn hoặc policy hash. Không tự cài MCP/repo/dependency.
Nếu engine thiếu khả năng cần thiết, ghi `BRAIN_CHANGE_REQUESTED` kèm bằng chứng rồi
dừng. Không tự sửa bộ não.

Video cuối dài 7–12 phút, chỉ có TTS Việt `BV074_streaming`; tắt hoàn toàn audio dub
Anh, không BGM, caption, speed, freeze, loop hoặc time-stretch.

## Gemini Ultra Web là cổng kiểm định duy nhất

Mọi kiểm định script, proxy và final phải đi qua lệnh `gemini-web run` của engine,
được điều khiển bằng Chrome hiển thị tại `https://gemini.google.com`. Dùng một profile
Chrome riêng cho dự án.
Người dùng tự đăng nhập đúng tài khoản Google AI Ultra ở lần đầu; không đọc, ghi,
copy hoặc lưu password/cookie. Không dùng Gemini API, MCP, tài khoản thường, model
thấp hơn hoặc fallback.

Engine tự mở chat mới, xác nhận account fingerprint khớp binding, kiểm tra plan Ultra và
chọn chính xác model `3.7 Flash` cùng mode `Tư duy mở rộng`. Nếu thiếu một điều kiện,
CAPTCHA, upload lỗi hoặc mất đăng nhập, dừng ở `CAN_CON_NGUOI_XU_LY`; không tự đoán và
không báo PASS. Gemini phải trả JSON-only theo request.

`gemini_web/<phase>/request.json` là danh sách nguồn duy nhất: upload đúng
`artifact_path` và mọi file trong `evidence_paths`, không lấy ảnh từ phase/run khác.
Chỉ engine operator được lưu raw response envelope, critic JSON, ảnh giao diện, request
và `operator_receipt.json`, sau đó ký receipt vào ledger HMAC. Antigravity **không tự tạo receipt**,
không tự tạo response/critic/screenshot và không khai PASS thay Gemini.
Engine từ chối mọi file thiếu hash, sai packet hoặc không có ledger entry. **Không dùng FFmpeg tạo ảnh phiên**;
screenshot phải đến từ DOM Chrome thật.

## Atomic beat

`Kich_ban/atomic_storyboard.json` là artifact biên tập chính. Một beat chỉ kể một
hành động, một phản ứng hoặc một ý bối cảnh. Nhiều shot được phép nằm trong một beat
nếu cùng minh họa đúng một ý.

Mỗi beat bắt buộc có scene/event/claim/source range/shot, `visual_fact`, nhân vật,
`sync_mode`, frame bằng chứng, một câu `narration_text`, ước lượng TTS và status.

- `ACTION`/`REACTION`: khai action window chính xác nằm trong source range. Hành động
  phải bắt đầu không muộn hơn 750 ms sau lúc footage/lời của beat bắt đầu; cửa sổ
  hành động phải dài ít nhất 1.500 ms và phủ ít nhất 35% TTS ước lượng, trừ hành động
  ngắn có bằng chứng rõ ràng.
- `CONTEXT`: action window là `null`, nhưng footage vẫn phải cùng tình huống.
- Hai hành động khác thời điểm phải tách hai beat.
- Khóa hình và visual fact trước, sau đó mới viết lời.
- TTS dài hơn hình: rút hoặc tách lời; không lấy cảnh sai nghĩa để lấp.
- Joke chỉ đổi cách kể, không bịa hành động, động cơ hay người nói.
- Tuyệt đối không chọn hình bằng công thức `source_start + thời lượng TTS`. Phải tìm
  đúng thời điểm hành động rồi mới chọn source range; nếu lời không vừa thì rút/tách
  lời hoặc thêm shot cùng đúng tình huống.
- Bỏ OP, ED, credits, next preview, title card, eyecatch, studio logo và cảnh không có
  giá trị review. Quét toàn tập vì các đoạn này có thể nằm giữa nội dung, không chỉ ở
  đầu hoặc cuối.

Dùng mẫu trong `Bo_nao_Antigravity/mau/atomic_storyboard.json`. Timestamp dùng mili
giây. Không suy ra đã xem hình chỉ từ transcript hoặc tên shot: phải mở frame/clip.
Với hành động nhanh, mở gói frame dày quanh action window.

## Producer và critic phải tách biệt

Lượt tạo storyboard là producer và ghi `producer_context_id`. Sau đó dùng một critic
context khác để lập `critic_script.json`; hai ID không được giống nhau. Critic mở lại
frame/clip và tìm sai người, sai hành động, lời đi trước/sau hình, nhiều hành động
trong một beat, văn dịch máy, lặp công thức, joke gượng và TTS dự kiến không vừa.

Sau khi storyboard hợp lệ, engine tạo
`atomic_evidence/source/anchors.json`. Critic script bắt buộc mở đủ START/MIDDLE/END
của mọi source range và ghi cụ thể `observed_visual`, `narration_summary`; không được
tự chế tên frame hoặc dùng evidence ngoài manifest.

Sau proxy, engine tạo `atomic_evidence/program/anchors.json`. Gemini Web phải mở contact
sheet dày do engine tạo, đối chiếu đủ ba anchor SOURCE với ba anchor PROGRAM của từng
range, rồi ghi `sync_verdict`. Nếu lời đi trước, theo sau, sai cảnh hoặc sai hành động
thì verdict và finding code phải nêu đúng lỗi. Không được tạo critic bằng vòng lặp điền
mặc định, không được để finding rỗng hàng loạt, không được copy cùng một mô tả cho
nhiều beat.
Không có trường `passed`; engine tự tính PASS từ bằng chứng. Dùng mẫu
`critic_script.json`, `critic_proxy.json` và `critic_final.json`; tất cả phải nằm trong
`gemini_web/<phase>/` của run, không ghi đè báo cáo của episode. Với JSON, dùng
`sync_verdict` nội bộ (`NOT_APPLICABLE`, `MATCH`, `VOICE_AHEAD`, `VOICE_BEHIND`,
`SCENE_MISMATCH`, `ACTION_MISMATCH`); các nhãn dễ hiểu như `VOICE_EARLY` phải được
ánh xạ sang mã nội bộ và lặp mã đó trong `finding_codes` nếu không phải `MATCH`.

## Trình tự một lần chạy

Sau mọi lệnh, đọc `next_action.json` và thực hiện đúng chỉ dẫn:

```powershell
uv run python run_episode.py prepare --run "<run_dir>"
uv run python run_episode.py validate --run "<run_dir>" --artifact truth
uv run python run_episode.py validate --run "<run_dir>" --artifact scene
uv run python run_episode.py validate --run "<run_dir>" --artifact storyboard
uv run python run_episode.py gemini-web run --run "<run_dir>" --phase script
uv run python run_episode.py tts --run "<run_dir>"
uv run python run_episode.py validate --run "<run_dir>" --artifact edl
uv run python run_episode.py render --run "<run_dir>" --quality proxy
uv run python run_episode.py gemini-web run --run "<run_dir>" --phase proxy
uv run python run_episode.py render --run "<run_dir>" --quality final
uv run python run_episode.py gemini-web run --run "<run_dir>" --phase final
uv run python run_episode.py audit --run "<run_dir>" --phase engine
```

Chỉ chạy lệnh phù hợp stage hiện tại; run có thể đã prepare trước. Nếu validation ghi
stage `SUA_BEAT`, chỉ sửa các beat/finding được nêu rồi chạy `resume` với phase mới
nhất: `script`, `tts` hoặc `video`.

```powershell
uv run python run_episode.py resume --run "<run_dir>" --phase video
```

Tối đa ba vòng; không làm lại beat sạch. TTS cache chỉ reuse trong cùng `revision_id` và
cùng SHA-256 nguồn; revision mới tự động miss để không dính audio cũ. Không xóa `_Cache`
trong lúc cùng revision.

## Văn phong

Viết như người Việt đang kể chuyện tự nhiên, gọn và có nhịp; hài hợp Gen Z 2026 nhưng
không cố nhét meme. Được dùng từ thô khi đúng cảm xúc. Tránh chuỗi câu mở bằng “lúc
này”, “ngay sau đó”, “không ngờ rằng”, tránh văn dịch và tính từ điện ảnh sáo rỗng.
Không dùng một khuôn câu lặp suốt tập. Ưu tiên động từ cụ thể và phản ứng thật trên
hình.

## Điều kiện dừng

Chỉ báo `HOAN_THANH` khi engine audit đã xuất
`Thanh_pham/review_anime.mp4`. Báo đường dẫn MP4, thời gian từng stage, cache hit/miss,
beat đã sửa và finding đã xử lý. Nếu stage là `CAN_CON_NGUOI_XU_LY` hoặc có
`BRAIN_CHANGE_REQUESTED`, báo đúng lỗi và dừng; không tuyên bố video đạt.

Engine audit sẽ chặn nếu thiếu metric thật của các stage storyboard, critic script,
TTS, proxy, critic video và final. Một báo cáo văn bản tự nhận PASS không thay thế
được metric, anchor hoặc validation.
