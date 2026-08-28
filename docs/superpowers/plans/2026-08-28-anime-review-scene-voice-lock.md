# Kế hoạch triển khai Scene/Shot/Beat và voice-lock

> Kế hoạch này triển khai phần mở rộng đã được duyệt trong
> `docs/superpowers/specs/2026-08-28-anime-review-mvp-design.md`.

## Mục tiêu

Biến scene thành đơn vị kể chuyện chính, giữ shot chính không bị cắt tùy tiện, liên
kết mọi voice cue với beat/event có bằng chứng, và để engine chỉ tạo EDL sau khi đo
thời lượng TTS thật. Antigravity vẫn là operator đa phương thức và tự chạy các vòng
quan sát–viết–sửa–render trong một agent run; engine không tự bịa hoặc sửa cốt truyện.

## Ràng buộc không đổi

- Một run chỉ nhận một video của một anime/mùa/tập.
- Đầu ra 7–12 phút, chỉ có TTS tiếng Việt `BV074_streaming`.
- Tắt hoàn toàn audio nguồn và không thêm BGM.
- Không speed-up, slow-down, freeze-frame, loop, đảo hình hoặc chèn cảnh vô nghĩa.
- Mâu thuẫn sự thật có dung sai bằng 0; coverage trực tiếp tối thiểu 0,80.
- Shot `MUST_KEEP` không được cắt chỉ vì cue ngắn; chỉ shot `OPTIONAL`/`TRANSITION`
  được ưu tiên cắt.
- Vẫn dùng JSON/dataclass hiện có, không thêm database, UI, batch hoặc API Gemini.
- Cổng văn phong độc lập: mỗi cue tối đa 240 ký tự, 2 câu, 4 mệnh đề; không tin cờ
  `directly_supported` do operator tự khai báo.

## Task 1 — Mở rộng hợp đồng dữ liệu

**Files:**

- Modify: `src/anime_review_mvp/models.py`
- Modify: `src/anime_review_mvp/jsonio.py` nếu cần cho nested tuple/dataclass
- Modify: các fixture JSON trong `Bo_nao_Antigravity/mau/`
- Test: `tests/unit/test_models.py`

Thêm các dataclass bất biến:

- `SceneShot(shot_id, start_ms, end_ms, role, event_ids, reason)` với role
  `MUST_KEEP | OPTIONAL | TRANSITION`.
- `SceneBeat(beat_id, start_ms, end_ms, event_ids, shot_ids, cue_ids)`.
- `ScenePacket(scene_id, start_ms, end_ms, story_purpose, event_ids, shots, beats,
  cue_ids)`.

Mở rộng `NarrationCue` để production có `scene_id` và `beat_ids`; mở rộng
`EdlSegment` để có `scene_id`, `shot_id`, `beat_id`, `event_ids`, `role`. Nếu giữ
default để tương thích fixture cũ, loader production vẫn phải yêu cầu field mới.
Các khoảng thời gian dùng integer milliseconds; mọi ID không rỗng và duy nhất trong
phạm vi artifact.

**Tests trước implementation:**

- Scene chứa nhiều shot theo đúng thứ tự nguồn.
- Không chấp nhận shot/beat nằm ngoài scene.
- Không chấp nhận role ngoài ba role quy định.
- Round-trip JSON UTF-8 giữ nguyên nested dataclass.
- Fixture cue/EDL cũ bị từ chối khi thiếu liên kết scene trong production.

## Task 2 — Validator scene packet và liên kết bằng chứng

**Files:**

- Modify: `src/anime_review_mvp/validation.py`
- Modify: `src/anime_review_mvp/antigravity.py`
- Test: `tests/unit/test_validation.py`
- Test: `tests/unit/test_antigravity_contract.py`

Thêm `validate_scene_packets(packets, truth, shots, source_duration_ms)` và các kiểm
tra:

1. Scene, shot, beat nằm trong duration nguồn và không có interval âm/rỗng.
2. Shot trong cùng scene được sắp theo nguồn, không chồng lấn ngoài ranh giới cho
   phép; beat tham chiếu shot tồn tại.
3. `MUST_KEEP` phải có ít nhất một event hoặc beat có bằng chứng; lý do cắt/giữ phải
   không rỗng.
4. Mọi event/claim/cue được tham chiếu đều tồn tại trong Truth/Script.
5. Một cue production thuộc đúng một scene; beat của cue phải thuộc scene đó.
6. Vùng `EXCLUDE` (OP/ED/credits/preview) không được xuất hiện trong packet trừ khi
   có quyết định `KEEP_STORY`.

Loader phải fail-closed với field lạ, ID trùng, cue/beat mồ côi và scene không có
shot/beat hợp lệ. Không dùng điểm số cảm tính để bỏ qua lỗi hard gate.

## Task 3 — Timing-fit và EDL có ngữ nghĩa

**Files:**

- Modify: `src/anime_review_mvp/validation.py`
- Modify: `src/anime_review_mvp/render.py` nếu cần program timing
- Modify: `src/anime_review_mvp/cli.py`
- Test: `tests/unit/test_validation.py`
- Test: `tests/unit/test_render.py`

Thêm các hàm thuần dữ liệu:

- `cue_source_duration(edl, cue_id)` tính tổng duration các đoạn hình của cue.
- `validate_voice_lock(packets, script, tts, edl, tolerance_ms=40)` kiểm tra mỗi cue
  có scene hợp lệ, các shot/beat/event đúng packet, và tổng hình khớp duration WAV
  thật trong ±40 ms.
- `build_edl_from_scene_packets(packets, script, tts)` chỉ tạo EDL từ các đoạn được
  operator chọn; không tự thêm cảnh ngoài packet.

Nếu duration không khớp, validator phải trả lỗi có owner rõ ràng:

- narration dài hơn hình hợp lệ → `SUA_NOI_DUNG` hoặc chia cue;
- narration ngắn hơn tổng `MUST_KEEP` → chia beat/cue hoặc sửa narration;
- chỉ thiếu thời lượng ở shot tùy chọn → `SUA_EDL` được cắt shot tùy chọn.

Thêm kiểm tra duration toàn tập 420–720 giây (`REVIEW_DURATION_OUT_OF_RANGE`) và
kiểm tra văn phong độc lập (`NARRATION_CUE_TOO_LONG`,
`NARRATION_TOO_MANY_SENTENCES`, `NARRATION_TOO_MANY_CLAUSES`,
`NARRATION_STYLE_OVERWRITTEN`). Các lỗi này được ghi vào
`Bao_cao/kiem_dinh_chat_luong.json` và route về `SUA_NOI_DUNG`.

Không đưa `atempo`, freeze, loop hoặc frame tĩnh vào filter graph. EDL phải giữ thứ tự
shot nguồn và tính được `program_start_ms/program_end_ms` từ duration đã đo.

## Task 4 — Hợp đồng operator Antigravity một lần chạy

**Files:**

- Modify: `Bo_nao_Antigravity/GEMINI.md`
- Modify: `src/anime_review_mvp/antigravity.py`
- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `src/anime_review_mvp/package.py`
- Add/modify: `Bo_nao_Antigravity/mau/scene_packets.json`
- Test: `tests/unit/test_workflow.py`
- Test: `tests/unit/test_package.py`

GEMINI.md phải yêu cầu đúng một agent run với các vòng nội bộ:

```text
QUAN_SAT → ScenePacket → VIET_KICH_BAN → TTS thật → voice-lock/EDL
→ render → xem lại MP4 → sửa đúng artifact lỗi → lặp lại
```

Antigravity phải xem scene/shot/beat trước khi viết cue; không viết từ danh sách shot
rời rạc. Khi lỗi, nó sửa artifact đúng owner rồi chạy validator lại, không chờ người
dùng duyệt từng stage. Giới hạn an toàn giữ tối đa ba vòng sửa cho một tập; kết thúc
`CAN_CON_NGUOI_XU_LY` nếu chưa đạt và không tạo PASS giả.

`build_operator_job` phải liệt kê artifact mới, thứ tự lệnh nội bộ và tiêu chí hoàn
thành. Báo cáo/ZIP phải chứa scene packet, timing decision, repair history và lỗi
voice-lock/văn phong để ChatGPT Web có đủ dữ liệu hướng dẫn vòng sau. Antigravity
phải chạy thêm vai trò `ADVERSARIAL_VERIFIER`: mở lại clip nguồn và MP4 cuối, đối
chiếu từng câu với shot đang phát; một cue đúng event nhưng có câu không được hình
chứng minh vẫn là lỗi.

Job phải kèm `write_policy` để operator biết rõ vùng được ghi và vùng chỉ đọc. Việc
muốn sửa prompt, mã nguồn, spec hoặc validator phải trở thành
`BRAIN_CHANGE_REQUESTED`, không được tự thực hiện trong agent run.

## Task 5 — Acceptance fixture cho scene nhiều shot

**Files:**

- Add: `tests/fixtures/operator_artifacts/scene_packets.json`
- Modify: `tests/fixtures/operator_artifacts/kich_ban_review.json`
- Modify: `tests/fixtures/operator_artifacts/edl.json`
- Add/modify: `tests/acceptance/test_episode_pipeline.py`

Fixture phải có ít nhất một scene gồm:

- hai shot `MUST_KEEP` chứa hành động chính;
- một shot `OPTIONAL` có thể cắt;
- hai beat neo vào các mốc khác nhau;
- một cue voice phủ nhiều shot nhưng thuộc cùng scene.

Acceptance phải chứng minh pipeline giả không mạng/model đi qua:

```text
start → prepare → scene validate → script validate → fake TTS đo WAV
→ voice-lock/EDL → render fixture → audit → package
```

Thêm case fail khi cắt `MUST_KEEP`, cue tham chiếu sai scene, voice duration lệch quá
40 ms, hoặc EDL đúng thời lượng nhưng thiếu `shot_id/beat_id/event_ids`.

## Task 6 — Cập nhật tài liệu và kiểm tra cuối

**Files:**

- Modify: `README.md`
- Modify: `Bo_nao_Antigravity/GEMINI.md` nếu còn lệch với spec
- Modify: `docs/superpowers/plans/2026-08-28-anime-review-mvp.md` chỉ khi cần liên
  kết kế hoạch cũ với migration này

README phải giải thích ngắn gọn scene/shot/beat, rằng người dùng chỉ giao một video
cho Antigravity và xem MP4 cuối, còn việc đo TTS/khớp EDL/kiểm định là tự động.

## Verification bắt buộc

Chạy sau mỗi task liên quan và chạy đầy đủ trước khi báo hoàn thành:

```powershell
uv run ruff check .
uv run pytest -v
git diff --check
git ls-files | rg -i "\.(mp4|mkv|mp3|wav|env)$"
git grep -n "ANIME_RECAP_TIKTOK_SESSION=" -- . ":!docs"
```

Kết quả mong đợi: ruff và toàn bộ test PASS; lệnh media/secret không trả về file
production hoặc credential. Chỉ sau khi có bằng chứng này mới được đóng gói hoặc nói
đã hoàn thành.
