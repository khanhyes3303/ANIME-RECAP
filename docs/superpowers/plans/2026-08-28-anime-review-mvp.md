# Anime Review MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Xây CLI tối giản để Antigravity xử lý một video anime dub tiếng Anh thành video review tiếng Việt 7–12 phút, chỉ có TTS BV074_streaming, kèm kiểm định và ZIP báo cáo.

**Architecture:** Một package Python điều khiển workspace theo anime/mùa/tập và cung cấp các subcommand xác định cho Antigravity. Antigravity tạo artifact biên tập JSON; engine chỉ xác thực timestamp, liên kết bằng chứng, TTS, EDL, render, audit, retry và cleanup, không tự quyết định nội dung.

**Tech Stack:** Python 3.12+, argparse, dataclasses/stdlib JSON, httpx, openai-whisper chạy local, FFmpeg/FFprobe trong PATH, pytest, ruff.

**Spec:** docs/superpowers/specs/2026-08-28-anime-review-mvp-design.md

## Global Constraints

- Một run chỉ xử lý một anime, một mùa, một tập và một video dub tiếng Anh.
- Video nguồn chỉ được đọc; không sửa, di chuyển, xóa hoặc sao chép vào thư mục tập.
- MP4 cuối dài 420–720 giây và có đúng một audio stream bắt nguồn từ TTS.
- Audio nguồn và nhạc nền không được map vào MP4 cuối.
- Không speed-up, slow-down, freeze, loop hoặc đảo video.
- TTS phải dùng TikTokCapCutProvider, voice BV074_streaming và ANIME_RECAP_TIKTOK_SESSION; không fallback.
- Tỷ lệ thời lượng cue được hỗ trợ trực tiếp phải đạt ít nhất 0.80; mọi mâu thuẫn sự thật có dung sai 0.
- Tổng cộng tối đa ba vòng sửa; sau đó phải kết thúc CAN_CON_NGUOI_XU_LY.
- Chỉ được xóa file dưới Tam_dang_xu_ly/<run_id> sau khi xác minh đường dẫn tuyệt đối.
- Không thêm UI, database, batch, caption, BGM, video dọc, web lookup, plugin hoặc CAS.

## File map

- pyproject.toml: metadata, dependency và cấu hình pytest/ruff.
- run_episode.py: entrypoint mỏng gọi anime_review_mvp.cli.main.
- src/anime_review_mvp/errors.py: MvpError duy nhất cho lỗi fail-closed.
- src/anime_review_mvp/models.py: toàn bộ hợp đồng JSON dạng dataclass.
- src/anime_review_mvp/jsonio.py: serialize/deserialize JSON UTF-8.
- src/anime_review_mvp/workspace.py: tên thư mục, JobPaths, source reference và cleanup boundary.
- src/anime_review_mvp/media.py: FFprobe, hash nguồn, Whisper tiếng Anh, shot boundaries và inspection assets.
- src/anime_review_mvp/validation.py: validator sổ sự thật, script, coverage, TTS manifest, EDL và audit.
- src/anime_review_mvp/tts.py: chunking, TikTok/CapCut provider, decode MP3 và tạo manifest TTS.
- src/anime_review_mvp/render.py: tạo FFmpeg filter graph, render video-only source + narration WAV và probe đầu ra.
- src/anime_review_mvp/workflow.py: state machine tuyến tính, repair counter và next_action.
- src/anime_review_mvp/package.py: báo cáo, ZIP và cleanup sau run.
- src/anime_review_mvp/cli.py: subcommand start, prepare, validate, tts, render, audit, package.
- Bo_nao_Antigravity/GEMINI.md: hiến pháp operator một tập.
- Bo_nao_Antigravity/mau/*.json: artifact mẫu không có dữ liệu anime cụ thể.
- tests/unit: test từng hợp đồng/ranh giới.
- tests/integration: FFmpeg fixture và pipeline giả không gọi mạng/model.
- README.md: đúng một luồng sử dụng MVP.

---

### Task 1: Khung dự án, hợp đồng dữ liệu và JSON

**Files:**
- Create: pyproject.toml
- Create: run_episode.py
- Create: src/anime_review_mvp/__init__.py
- Create: src/anime_review_mvp/errors.py
- Create: src/anime_review_mvp/models.py
- Create: src/anime_review_mvp/jsonio.py
- Test: tests/unit/test_models.py

**Interfaces:**
- Produces: MvpError; Event, SourceRegionAnnotation, TruthDocument, Claim, NarrationCue, ScriptDocument, TtsCue, TtsManifest, EdlSegment, EdlDocument, AuditFinding, AuditReport dataclasses; dump_json(path, value) và load_json(path, cls).
- Consumes: chỉ Python stdlib.

- [ ] **Step 1: Viết failing tests cho invariant cơ bản**

    from pathlib import Path
    import pytest

    from anime_review_mvp.errors import MvpError
    from anime_review_mvp.jsonio import dump_json, load_json
    from anime_review_mvp.models import Event, Claim, NarrationCue, ScriptDocument

    def test_event_and_claim_require_positive_intervals_and_evidence(tmp_path: Path) -> None:
        with pytest.raises(MvpError):
            Event("E001", 2000, 1000, ("A",), "sai", "CORE", 1.0)
        with pytest.raises(MvpError):
            Claim("C001", "ACTION", "A chạy", ())

    def test_script_round_trip_is_utf8_and_exact(tmp_path: Path) -> None:
        script = ScriptDocument((
            NarrationCue("N001", "Cậu này chạy như bị dí KPI.", ("C001",), ("E001",)),
        ))
        path = tmp_path / "script.json"
        dump_json(path, script)
        assert load_json(path, ScriptDocument) == script

- [ ] **Step 2: Chạy test để xác nhận thất bại**

    uv run pytest tests/unit/test_models.py -v

Expected: collection FAIL vì package anime_review_mvp chưa tồn tại.

- [ ] **Step 3: Tạo dataclass tối thiểu và JSON codec**

    @dataclass(frozen=True, slots=True)
    class Event:
        event_id: str
        start_ms: int
        end_ms: int
        characters: tuple[str, ...]
        description: str
        importance: str
        confidence: float

        def __post_init__(self) -> None:
            if not self.event_id or self.start_ms < 0 or self.end_ms <= self.start_ms:
                raise MvpError("event interval is invalid")
            if not self.description.strip() or not 0 <= self.confidence <= 1:
                raise MvpError("event content is invalid")

    @dataclass(frozen=True, slots=True)
    class Claim:
        claim_id: str
        kind: str
        text: str
        evidence_event_ids: tuple[str, ...]

        def __post_init__(self) -> None:
            if not self.claim_id or not self.text.strip() or not self.evidence_event_ids:
                raise MvpError("claim requires factual evidence")

    @dataclass(frozen=True, slots=True)
    class SourceRegionAnnotation:
        region_id: str
        start_ms: int
        end_ms: int
        kind: str
        decision: str
        reason: str

        def __post_init__(self) -> None:
            if self.kind not in {"OPENING", "ENDING", "CREDITS", "NEXT_PREVIEW", "OTHER"}:
                raise MvpError("source region kind is invalid")
            if self.decision not in {"EXCLUDE", "KEEP_STORY"} or not self.reason.strip():
                raise MvpError("source region decision requires an explicit reason")

    @dataclass(frozen=True, slots=True)
    class TruthDocument:
        events: tuple[Event, ...]
        source_regions: tuple[SourceRegionAnnotation, ...]
        source_region_scan_complete: bool

        def __post_init__(self) -> None:
            if not self.events or not self.source_region_scan_complete:
                raise MvpError("truth document requires events and a completed source-region scan")

Use một registry TYPE_BY_NAME trong jsonio.py để tái dựng tuple/dataclass; không dùng pickle hoặc eval.

- [ ] **Step 4: Chạy unit tests và lint**

    uv run pytest tests/unit/test_models.py -v
    uv run ruff check src tests run_episode.py

Expected: PASS.

- [ ] **Step 5: Commit**

    git add pyproject.toml run_episode.py src/anime_review_mvp tests/unit/test_models.py
    git commit -m "feat: add minimal recap data contracts"

---

### Task 2: Workspace theo anime và ranh giới nguồn/temp

**Files:**
- Create: src/anime_review_mvp/workspace.py
- Test: tests/unit/test_workspace.py

**Interfaces:**
- Consumes: MvpError và dump_json từ Task 1.
- Produces: JobKey, JobPaths; create_job(root, anime, season, episode, video) -> JobPaths; assert_inside_run(path, run_root) -> Path; cleanup_run(run_root) -> None.

- [ ] **Step 1: Viết failing tests cho cấu trúc và chống xóa nhầm**

    def test_create_job_uses_anime_season_episode_hierarchy(tmp_path: Path) -> None:
        video = tmp_path / "episode.mp4"
        video.write_bytes(b"source")
        paths = create_job(tmp_path, "Frieren", 1, 2, video)
        assert paths.episode_dir == tmp_path / "Kho_Anime" / "Frieren" / "Mua_01" / "Tap_002"
        assert paths.temp_dir.parent == tmp_path / "Tam_dang_xu_ly"
        assert video.exists()

    def test_cleanup_rejects_any_target_outside_run(tmp_path: Path) -> None:
        run = tmp_path / "Tam_dang_xu_ly" / "run-1"
        run.mkdir(parents=True)
        with pytest.raises(MvpError):
            assert_inside_run(tmp_path / "Kho_Anime", run)

- [ ] **Step 2: Chạy test để xác nhận thất bại**

    uv run pytest tests/unit/test_workspace.py -v

Expected: FAIL vì create_job chưa tồn tại.

- [ ] **Step 3: Implement JobPaths và cleanup fail-closed**

    def assert_inside_run(path: Path, run_root: Path) -> Path:
        resolved = path.resolve(strict=False)
        root = run_root.resolve(strict=True)
        if resolved == root or root not in resolved.parents:
            raise MvpError("cleanup target is outside the exact run directory")
        return resolved

    def cleanup_run(run_root: Path) -> None:
        root = run_root.resolve(strict=True)
        expected = (root.parent.name == "Tam_dang_xu_ly")
        if not expected:
            raise MvpError("run directory is not under Tam_dang_xu_ly")
        shutil.rmtree(root)

create_job phải tạo bảy thư mục tập, một temp UUID, từ chối season/episode < 1 và từ chối khi Thanh_pham đã có MP4.

- [ ] **Step 4: Chạy tests**

    uv run pytest tests/unit/test_workspace.py -v
    uv run pytest tests/unit -v

Expected: PASS và video nguồn còn nguyên.

- [ ] **Step 5: Commit**

    git add src/anime_review_mvp/workspace.py tests/unit/test_workspace.py
    git commit -m "feat: add per-episode workspace boundary"

---

### Task 3: Probe nguồn, transcript tiếng Anh và inspection assets

**Files:**
- Create: src/anime_review_mvp/media.py
- Test: tests/unit/test_media.py
- Test: tests/integration/test_media_ffmpeg.py
- Create: tests/fixtures/make_fixture.py

**Interfaces:**
- Consumes: JobPaths, SourceRef, Event-like transcript/shot models, dump_json.
- Produces: probe_source(video, run) -> SourceRef; transcribe_english(video, output, model_name="small") -> TranscriptDocument; detect_shots(video, duration_ms, runner) -> tuple[Shot, ...]; extract_inspection_assets(video, shots, output_dir, runner) -> tuple[Path, ...].

- [ ] **Step 1: Viết failing tests cho FFprobe và transcript adapter**

    def test_probe_rejects_missing_video_stream(tmp_path: Path) -> None:
        runner = FakeRunner(stdout='{"format":{"duration":"10"},"streams":[]}')
        with pytest.raises(MvpError):
            probe_source(tmp_path / "x.mp4", runner=runner)

    def test_transcribe_forces_english_and_persists_word_times(tmp_path: Path) -> None:
        model = FakeWhisperModel({
            "language": "en",
            "segments": [{"start": 1.0, "end": 2.0, "text": "Run!", "words": [
                {"start": 1.0, "end": 1.5, "word": "Run"}
            ]}],
        })
        doc = transcribe_english(tmp_path / "episode.mp4", tmp_path / "transcript.json", model=model)
        assert doc.language == "en"
        assert doc.segments[0].start_ms == 1000
        assert model.options["language"] == "en"

- [ ] **Step 2: Chạy unit test để xác nhận thất bại**

    uv run pytest tests/unit/test_media.py -v

Expected: FAIL vì media.py chưa tồn tại.

- [ ] **Step 3: Implement probe, Whisper adapter và FFmpeg scene cuts**

    def transcribe_english(video: Path, output: Path, *, model=None, model_name="small"):
        whisper_model = model or whisper.load_model(model_name)
        raw = whisper_model.transcribe(
            str(video), language="en", task="transcribe", word_timestamps=True, verbose=False
        )
        if raw.get("language") != "en":
            raise MvpError("English dub transcription did not resolve as English")
        document = TranscriptDocument.from_whisper(raw)
        dump_json(output, document)
        return document

detect_shots gọi FFmpeg select=gt(scene\,0.30),showinfo, parse pts_time, luôn thêm 0 và duration làm biên. extract_inspection_assets lấy một JPEG giữa mỗi shot và clip context chỉ trong temp run.

- [ ] **Step 4: Tạo fixture FFmpeg 3 giây và chạy integration test**

    uv run python tests/fixtures/make_fixture.py
    uv run pytest tests/integration/test_media_ffmpeg.py -v

Expected: SourceRef có một video stream; shot intervals nằm trong duration; không tạo artifact ngoài temp.

- [ ] **Step 5: Commit**

    git add src/anime_review_mvp/media.py tests/unit/test_media.py tests/integration/test_media_ffmpeg.py tests/fixtures
    git commit -m "feat: prepare English-dub episode evidence"

---

### Task 4: Bộ não Antigravity và hợp đồng artifact

**Files:**
- Create: Bo_nao_Antigravity/GEMINI.md
- Create: Bo_nao_Antigravity/mau/su_that_tap_phim.json
- Create: Bo_nao_Antigravity/mau/kich_ban_review.json
- Create: Bo_nao_Antigravity/mau/kiem_dinh.json
- Create: src/anime_review_mvp/antigravity.py
- Test: tests/unit/test_antigravity_contract.py

**Interfaces:**
- Consumes: SourceRef, TranscriptDocument, Shot list và models Task 1.
- Produces: build_operator_job(paths, source, transcript, shots) -> Path; load_truth(path) -> TruthDocument; load_script(path) -> ScriptDocument; load_audit(path) -> AuditReport.

- [ ] **Step 1: Viết failing tests cho ba vai trò tách biệt**

    def test_truth_rejects_jokes_and_unbounded_events(tmp_path: Path) -> None:
        payload = truth_payload()
        payload["events"][0]["editorial_joke"] = "thanh niên báo đời"
        with pytest.raises(MvpError):
            load_truth(write_json(tmp_path, payload))

    def test_script_requires_claim_and_event_binding(tmp_path: Path) -> None:
        payload = script_payload()
        payload["cues"][0]["event_ids"] = []
        with pytest.raises(MvpError):
            load_script(write_json(tmp_path, payload))

    def test_audit_cannot_pass_with_contradiction(tmp_path: Path) -> None:
        payload = audit_payload(passed=True, findings=[{"severity":"ERROR","code":"FACT_CONTRADICTION"}])
        with pytest.raises(MvpError):
            load_audit(write_json(tmp_path, payload))

    def test_truth_requires_completed_op_ed_scan(tmp_path: Path) -> None:
        payload = truth_payload()
        payload["source_region_scan_complete"] = False
        with pytest.raises(MvpError, match="source-region"):
            load_truth(write_json(tmp_path, payload))

- [ ] **Step 2: Chạy test để xác nhận thất bại**

    uv run pytest tests/unit/test_antigravity_contract.py -v

Expected: FAIL vì loader và template chưa tồn tại.

- [ ] **Step 3: Viết GEMINI.md và loader strict**

GEMINI.md phải chứa đúng luồng:

    1. QUAN_SAT: chỉ mô tả sự kiện nhìn/nghe được; không viết review.
    2. VIET_KICH_BAN: chỉ dùng event_id đã tồn tại; tách atomic claims.
    3. KIEM_DINH: xem clip ứng với cue và MP4 cuối; không tự cho qua.
    4. Khi thiếu bằng chứng: bỏ/sửa câu hoặc trả CAN_CON_NGUOI_XU_LY.
    5. Cấm đổi cốt truyện, sai người nói, speed/freeze/loop và xử lý tập khác.
    6. Đánh dấu OPENING, ENDING, CREDITS, NEXT_PREVIEW là EXCLUDE; cold open hoặc
       post-credit có cốt truyện phải là KEEP_STORY với lý do nhìn thấy được.
    7. Ưu tiên cốt truyện chính, thiết lập quan trọng về sau, hành động, phản ứng,
       fan-service và tình huống hài có giá trị; bỏ cảnh thường không đóng góp.

load_* phải từ chối field lạ ở cấp contract, ID trùng, timestamp ngoài source và PASS khi còn finding ERROR.

- [ ] **Step 4: Chạy tests và kiểm tra template parse được**

    uv run pytest tests/unit/test_antigravity_contract.py -v
    uv run python -m json.tool Bo_nao_Antigravity/mau/su_that_tap_phim.json
    uv run python -m json.tool Bo_nao_Antigravity/mau/kich_ban_review.json
    uv run python -m json.tool Bo_nao_Antigravity/mau/kiem_dinh.json

Expected: PASS.

- [ ] **Step 5: Commit**

    git add Bo_nao_Antigravity src/anime_review_mvp/antigravity.py tests/unit/test_antigravity_contract.py
    git commit -m "feat: define Antigravity episode contract"

---

### Task 5: Validator sự thật, coverage 80% và EDL

**Files:**
- Create: src/anime_review_mvp/validation.py
- Test: tests/unit/test_validation.py

**Interfaces:**
- Consumes: TruthDocument, ScriptDocument, TtsManifest, EdlDocument, AuditReport.
- Produces: validate_truth(truth, source_duration_ms); validate_script(script, truth); coverage_ratio(script, tts) -> Decimal; validate_edl(edl, source_duration_ms, tts, truth); validate_audit(audit, coverage).

- [ ] **Step 1: Viết failing tests cho 0.80 và dung sai 0**

    def test_coverage_is_weighted_by_real_tts_duration() -> None:
        script = script_with_supported_flags([True, True, False])
        tts = tts_manifest([4000, 4000, 2000])
        assert coverage_ratio(script, tts) == Decimal("0.8")

    def test_coverage_below_threshold_fails() -> None:
        with pytest.raises(MvpError, match="0.80"):
            validate_audit(clean_audit(), Decimal("0.799"))

    def test_one_fact_contradiction_fails_even_with_full_coverage() -> None:
        audit = audit_with_error("FACT_CONTRADICTION")
        with pytest.raises(MvpError, match="FACT_CONTRADICTION"):
            validate_audit(audit, Decimal("1"))

    def test_edl_requires_enough_one_to_one_footage_for_each_cue() -> None:
        with pytest.raises(MvpError, match="footage duration"):
            validate_edl(
                edl_for_cue(source_ms=3000), 10000, tts_manifest([4000]), clean_truth()
            )

    def test_edl_rejects_excluded_opening_or_ending_region() -> None:
        truth = truth_with_region(0, 90000, kind="OPENING", decision="EXCLUDE")
        with pytest.raises(MvpError, match="excluded source region"):
            validate_edl(edl_for_source_interval(1000, 5000), 1200000, tts_manifest([4000]), truth)

- [ ] **Step 2: Chạy test để xác nhận thất bại**

    uv run pytest tests/unit/test_validation.py -v

Expected: FAIL vì validation.py chưa tồn tại.

- [ ] **Step 3: Implement validator bằng integer milliseconds/Decimal**

    def coverage_ratio(script: ScriptDocument, tts: TtsManifest) -> Decimal:
        durations = {cue.cue_id: cue.duration_ms for cue in tts.cues}
        total = sum(durations.values())
        supported = sum(
            durations[cue.cue_id] for cue in script.cues if cue.directly_supported
        )
        if total <= 0:
            raise MvpError("TTS duration must be positive")
        return Decimal(supported) / Decimal(total)

validate_edl phải kiểm tra source bounds, chronology trong từng cue, cue ID tồn tại,
tổng source duration mỗi cue bằng duration WAV trong sai số tối đa 40 ms và không
giao với SourceRegionAnnotation có decision EXCLUDE. Vùng KEEP_STORY được phép dùng
vì đã có lý do cốt truyện. Model không có field speed/freeze/loop.

- [ ] **Step 4: Chạy toàn bộ unit tests**

    uv run pytest tests/unit -v
    uv run ruff check src tests

Expected: PASS.

- [ ] **Step 5: Commit**

    git add src/anime_review_mvp/validation.py tests/unit/test_validation.py
    git commit -m "feat: enforce evidence coverage and edit rules"

---

### Task 6: Port TTS BV074_streaming tối thiểu

**Files:**
- Create: src/anime_review_mvp/tts.py
- Test: tests/unit/test_tts.py

**Interfaces:**
- Consumes: ScriptDocument.
- Produces: normalize_speech_text(text) -> str; plan_chunks(text, character_ceiling=150) -> tuple[str, ...]; TikTokCapCutProvider.synthesize(chunks, profile, policy); synthesize_script(script, output_dir, provider=None) -> TtsManifest.

- [ ] **Step 1: Viết failing tests cho chunking/provider/manifest**

    def test_vietnamese_chunks_reconstruct_exact_text() -> None:
        text = "Cậu này vừa vào lớp, đã bị dí KPI. Đúng là hết cứu!"
        chunks = plan_chunks(text, character_ceiling=30)
        assert " ".join(chunks) == normalize_speech_text(text)

    def test_provider_retries_503_and_keeps_exact_voice(monkeypatch) -> None:
        monkeypatch.setenv("ANIME_RECAP_TIKTOK_SESSION", "opaque")
        provider = TikTokCapCutProvider(httpx.Client(transport=retry_then_mp3()))
        result = provider.synthesize(("xin chào",), default_profile(), default_policy())
        assert result.chunks[0].attempts == 2
        assert dict(result.safe_metadata)["voice_id"] == "BV074_streaming"

    def test_missing_session_never_falls_back(monkeypatch) -> None:
        monkeypatch.delenv("ANIME_RECAP_TIKTOK_SESSION", raising=False)
        with pytest.raises(MvpError, match="ANIME_RECAP_TIKTOK_SESSION"):
            TikTokCapCutProvider().synthesize(("xin chào",), default_profile(), default_policy())

- [ ] **Step 2: Chạy test để xác nhận thất bại**

    uv run pytest tests/unit/test_tts.py -v

Expected: FAIL vì tts.py chưa tồn tại.

- [ ] **Step 3: Port hành vi V4 và bỏ bureaucracy**

Giữ endpoint:

    https://api16-normal-v6.tiktokv.com/media/api/text/speech/invoke/

default_profile phải cố định vi-VN, BV074_streaming, MP3, PCM s16le, 24000 Hz mono và credential env ANIME_RECAP_TIKTOK_SESSION. synthesize_script tạo MP3/WAV riêng theo cue, đo duration WAV bằng wave module, ghép narration.wav không gap và ghi tts_manifest.json. Không port authority, CAS, immutable revision hoặc human approval V4.

- [ ] **Step 4: Chạy tests không gọi mạng thật**

    uv run pytest tests/unit/test_tts.py -v
    uv run pytest tests/unit -v

Expected: PASS; MockTransport nhận đúng voice ID; không có HTTP thật.

- [ ] **Step 5: Commit**

    git add src/anime_review_mvp/tts.py tests/unit/test_tts.py
    git commit -m "feat: preserve Vietnamese TikTok TTS behavior"

---

### Task 7: Renderer EDL với TTS-only

**Files:**
- Create: src/anime_review_mvp/render.py
- Test: tests/unit/test_render.py
- Test: tests/integration/test_render_ffmpeg.py

**Interfaces:**
- Consumes: SourceRef, EdlDocument, TtsManifest và narration.wav.
- Produces: build_filter_graph(edl) -> str; render_review(source, narration_wav, edl, output, runner) -> RenderResult; probe_render(output) -> RenderResult.

- [ ] **Step 1: Viết failing tests chống audio nguồn và time manipulation**

    def test_filter_graph_only_trims_and_concats_video() -> None:
        graph = build_filter_graph(two_segment_edl())
        assert "trim=start=" in graph
        assert "setpts=PTS-STARTPTS" in graph
        assert "concat=n=2:v=1:a=0" in graph
        for forbidden in ("atempo", "setpts=PTS/", "loop", "tpad", "freeze"):
            assert forbidden not in graph

    def test_ffmpeg_maps_only_rendered_video_and_tts_audio() -> None:
        command = build_render_command(Path("source.mp4"), Path("narration.wav"), edl(), Path("out.mp4"))
        assert command.count("-map") == 2
        assert "1:a:0" in command
        assert "0:a" not in command

- [ ] **Step 2: Chạy unit test để xác nhận thất bại**

    uv run pytest tests/unit/test_render.py -v

Expected: FAIL vì render.py chưa tồn tại.

- [ ] **Step 3: Implement FFmpeg trim/concat và output probe**

    def build_render_command(source, narration, edl, output):
        return [
            "ffmpeg", "-y", "-v", "error", "-i", str(source), "-i", str(narration),
            "-filter_complex", build_filter_graph(edl),
            "-map", "[video]", "-map", "1:a:0",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-movflags", "+faststart", str(output),
        ]

probe_render dùng ffprobe JSON và yêu cầu đúng một video stream, đúng một audio stream, duration 420–720 giây ở production. Integration test truyền allow_short_fixture=True chỉ trong API test, không expose ở CLI production.

- [ ] **Step 4: Render fixture và xác nhận stream mapping**

    uv run pytest tests/integration/test_render_ffmpeg.py -v

Expected: PASS; audio output hash/độ dài khớp narration fixture; source audio tone không xuất hiện.

- [ ] **Step 5: Commit**

    git add src/anime_review_mvp/render.py tests/unit/test_render.py tests/integration/test_render_ffmpeg.py
    git commit -m "feat: render one-to-one TTS-only review video"

---

### Task 8: Workflow, ba vòng sửa và CLI operator

**Files:**
- Create: src/anime_review_mvp/workflow.py
- Create: src/anime_review_mvp/cli.py
- Modify: run_episode.py
- Test: tests/unit/test_workflow.py
- Test: tests/unit/test_cli.py

**Interfaces:**
- Consumes: mọi service Tasks 2–7.
- Produces: Stage enum; RunState; start_job(args) -> RunState; advance(run_dir, expected, target); record_repair(run_dir, owner, codes) -> RunState; main(argv=None) -> int.

- [ ] **Step 1: Viết failing tests cho transition và retry**

    def test_state_machine_is_linear_and_fail_closed(tmp_path: Path) -> None:
        state = new_state(tmp_path)
        with pytest.raises(MvpError):
            advance(state.run_dir, Stage.CHUAN_BI, Stage.TAO_TTS)

    def test_third_failed_repair_becomes_human_required(tmp_path: Path) -> None:
        state = new_state(tmp_path)
        for _ in range(3):
            state = record_repair(state.run_dir, "SUA_NOI_DUNG", ("UNSUPPORTED_CLAIM",))
        assert state.stage is Stage.CAN_CON_NGUOI_XU_LY
        with pytest.raises(MvpError):
            record_repair(state.run_dir, "SUA_NOI_DUNG", ("UNSUPPORTED_CLAIM",))

    def test_cli_start_accepts_exactly_one_video(tmp_path: Path) -> None:
        result = main(["start", "--anime", "Frieren", "--season", "1", "--episode", "1",
                       "--video", str(tmp_path / "ep.mp4")])
        assert result == 0

- [ ] **Step 2: Chạy test để xác nhận thất bại**

    uv run pytest tests/unit/test_workflow.py tests/unit/test_cli.py -v

Expected: FAIL vì workflow/cli chưa tồn tại.

- [ ] **Step 3: Implement state JSON và subcommands**

Allowed transitions phải là:

    CHUAN_BI -> QUAN_SAT -> VIET_KICH_BAN -> KIEM_DINH_KICH_BAN
    -> TAO_TTS -> LAP_EDL -> DUNG_VIDEO -> KIEM_DINH_VIDEO
    -> DONG_GOI -> HOAN_THANH

Subcommand validate nhận loại artifact và chỉ advance khi validator tương ứng PASS. Subcommand audit route lỗi về QUAN_SAT, VIET_KICH_BAN hoặc LAP_EDL theo code; không cho operator tự đặt stage HOAN_THANH.

- [ ] **Step 4: Chạy unit suite và CLI help**

    uv run pytest tests/unit -v
    uv run python run_episode.py --help
    uv run python run_episode.py start --help

Expected: PASS; help chỉ liệt kê start/prepare/validate/tts/render/audit/package, không có batch/publish.

- [ ] **Step 5: Commit**

    git add src/anime_review_mvp/workflow.py src/anime_review_mvp/cli.py run_episode.py tests/unit
    git commit -m "feat: orchestrate one Antigravity episode run"

---

### Task 9: Báo cáo, ZIP và cleanup

**Files:**
- Create: src/anime_review_mvp/package.py
- Test: tests/unit/test_package.py

**Interfaces:**
- Consumes: RunState, source ref, truth, script, TTS, EDL, audit và render result.
- Produces: build_report(run_dir) -> tuple[Path, Path]; create_handoff_zip(run_dir, destination) -> Path; finalize_run(run_dir, passed) -> FinalizationResult.

- [ ] **Step 1: Viết failing tests cho nội dung ZIP và cleanup**

    def test_zip_contains_reports_but_no_video_bytes(tmp_path: Path) -> None:
        run = completed_run(tmp_path)
        archive = create_handoff_zip(run, tmp_path / "handoff.zip")
        with ZipFile(archive) as zipped:
            names = set(zipped.namelist())
        assert {"bao_cao.md", "bao_cao.json", "kich_ban_review.json", "edl.json"} <= names
        assert not any(name.endswith((".mp4", ".mkv")) for name in names)

    def test_finalize_preserves_source_and_episode_artifacts(tmp_path: Path) -> None:
        run, source, final = completed_run_with_files(tmp_path)
        finalize_run(run, passed=True)
        assert source.exists()
        assert final.exists()
        assert not run.exists()

- [ ] **Step 2: Chạy test để xác nhận thất bại**

    uv run pytest tests/unit/test_package.py -v

Expected: FAIL vì package.py chưa tồn tại.

- [ ] **Step 3: Implement report/ZIP allowlist và safe cleanup**

ZIP allowlist cố định:

    bao_cao.md
    bao_cao.json
    su_that_tap_phim.json
    kich_ban_review.json
    tts_manifest.json
    edl.json
    kiem_dinh.json
    run_state.json

bao_cao.json chứa absolute path + SHA-256 của source/final MP4, tool versions, repair history và PASS hoặc CAN_CON_NGUOI_XU_LY. finalize_run chuyển evidence nhỏ cần giữ sang Bao_cao trước khi gọi cleanup_run.

- [ ] **Step 4: Chạy tests**

    uv run pytest tests/unit/test_package.py -v
    uv run pytest tests/unit -v

Expected: PASS.

- [ ] **Step 5: Commit**

    git add src/anime_review_mvp/package.py tests/unit/test_package.py
    git commit -m "feat: package auditable episode handoff"

---

### Task 10: Acceptance slice và tài liệu vận hành

**Files:**
- Create: tests/acceptance/test_episode_pipeline.py
- Create: tests/fixtures/operator_artifacts/*.json
- Create: README.md
- Create: .gitignore
- Modify: Bo_nao_Antigravity/GEMINI.md

**Interfaces:**
- Consumes: public CLI và toàn bộ artifact contracts.
- Produces: một acceptance path prepare -> operator fixtures -> validate -> fake TTS -> render -> audit -> package; tài liệu chạy thật.

- [ ] **Step 1: Viết acceptance test thất bại**

    def test_one_episode_reaches_package_without_network_or_real_model(tmp_path: Path) -> None:
        source = make_av_fixture(tmp_path, seconds=8)
        job = cli_start(tmp_path, source)
        cli_prepare(job, fake_transcript=True)
        copy_operator_fixtures(job)
        cli_validate_truth_and_script(job)
        cli_tts(job, provider=FakeTtsProvider(seconds=8))
        cli_render(job, allow_short_fixture=True)
        cli_audit(job, fixture_audit="PASS")
        archive = cli_package(job)
        assert archive.exists()
        assert read_state(job).stage is Stage.HOAN_THANH
        assert_final_has_tts_only(job)

- [ ] **Step 2: Chạy acceptance test để xác nhận thất bại**

    uv run pytest tests/acceptance/test_episode_pipeline.py -v

Expected: FAIL ở public CLI gap đầu tiên; sửa wiring, không nới validator.

- [ ] **Step 3: Hoàn thiện wiring nhỏ nhất và README**

README chỉ ghi:

    1. Cài Python/uv và FFmpeg.
    2. uv sync --dev.
    3. Đặt ANIME_RECAP_TIKTOK_SESSION.
    4. Giao một video cho Antigravity bằng lệnh start.
    5. Đọc next_action.json; không chạy batch.
    6. Thành phẩm nằm trong Kho_Anime/.../Thanh_pham.
    7. ZIP nằm trong Goi_gui_ChatGPT_Web.

.gitignore phải loại .venv, Tam_dang_xu_ly, video/audio thực, cache Whisper và secret env; không ignore JSON báo cáo/fixture.

- [ ] **Step 4: Chạy verification đầy đủ**

    uv sync --dev
    uv run ruff check .
    uv run pytest -v
    git status --short

Expected: ruff PASS; toàn bộ test PASS; chỉ file dự kiến được track; không có video/audio thật hoặc credential trong Git.

- [ ] **Step 5: Commit**

    git add README.md .gitignore Bo_nao_Antigravity tests/acceptance tests/fixtures
    git commit -m "test: verify minimal episode review pipeline"

---

## Final verification

- [ ] Chạy lại toàn bộ test trong môi trường sạch:

    uv sync --dev
    uv run ruff check .
    uv run pytest -v

- [ ] Kiểm tra secret và file media không lọt vào Git:

    git ls-files | rg -i "\.(mp4|mkv|mp3|wav|env)$"
    git grep -n "ANIME_RECAP_TIKTOK_SESSION=" -- . ":!docs"

Expected: cả hai lệnh không trả về credential hoặc media production.

- [ ] Kiểm tra phạm vi CLI:

    uv run python run_episode.py --help

Expected: không có UI, batch, publish, BGM, caption hoặc vertical command.

- [ ] Kiểm tra lịch sử commit:

    git log --oneline --decorate -12

Expected: mỗi task có commit riêng, không trộn thay đổi ngoài MVP.
