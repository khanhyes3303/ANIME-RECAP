# Phương án B khóa câu–cảnh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Xây pipeline lai trong đó Antigravity cung cấp bản phân tích/lời nháp, còn Codex khóa từng câu TTS với đúng khoảng hình và là bên duy nhất xác nhận ngữ nghĩa video cuối.

**Architecture:** Giữ artifact hiện tại của Antigravity làm dữ liệu tư vấn, rồi thêm artifact `khoa_cau_canh.json` do Codex sở hữu. TTS, EDL và render chỉ tiêu thụ các span đã khóa; engine tự đo duration, chặn micro-clip, trích ảnh kiểm định và tính PASS kỹ thuật, không tin cờ PASS do Antigravity viết.

**Tech Stack:** Python 3.12, dataclass JSON contracts, FFmpeg/FFprobe, Whisper hiện có, TTS `BV074_streaming`, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-08-28-phuong-an-b-codex-bien-tap-design.md`

## Global Constraints

- Mỗi run chỉ xử lý đúng một tập anime dub tiếng Anh.
- Thành phẩm dài 420–720 giây và chỉ có TTS tiếng Việt; không audio nguồn, BGM, caption hoặc batch.
- Không speed, freeze, loop, time-stretch hoặc chèn hình vô nghĩa để lấp thời lượng.
- Một span chứa đúng một câu hoặc một ý nói liền mạch, gắn với một hành động/phản ứng có bằng chứng.
- Tổng thời lượng được hình hỗ trợ trực tiếp phải đạt ít nhất 0.80; cảnh hành động, tiết lộ, nhân quả và payoff chính không được phép lệch.
- Chênh lệch đuôi video/audio tối đa 80 ms.
- Đoạn EDL ngắn hơn 500 ms bị chặn, trừ ngoại lệ hành động được Codex ghi rõ.
- Antigravity không được sửa artifact khóa của Codex hoặc tự cấp PASS cuối.
- Không ZIP, không ChatGPT Web và không tự dọn tài nguyên sau run.
- Render mới ở dạng candidate trong run; chỉ thay thành phẩm hiện tại sau khi engine audit PASS và đã lưu bản cũ vào `Bao_cao/phien_ban_cu`.
- Không thêm PySceneDetect, WhisperX, wrapper FFmpeg hoặc repo ngoài trong lượt triển khai đầu tiên.

## File Structure

- Modify: `src/anime_review_mvp/models.py` — hợp đồng span, nguồn hình, TTS, EDL, ảnh neo và đánh giá Codex.
- Modify: `src/anime_review_mvp/antigravity.py` — tách output nháp Antigravity khỏi artifact chỉ đọc của Codex.
- Create: `src/anime_review_mvp/editorial.py` — load/validate artifact khóa câu–cảnh do Codex tạo.
- Modify: `src/anime_review_mvp/media.py` — trích ảnh neo đầu–giữa–cuối từ nguồn và MP4 cuối.
- Modify: `src/anime_review_mvp/tts.py` — tạo một WAV cho mỗi span đã khóa.
- Create: `src/anime_review_mvp/edl.py` — sinh EDL trực tiếp từ source range do Codex chọn, không cắt cơ học raw shot.
- Modify: `src/anime_review_mvp/validation.py` — cổng span, micro-clip, duration, coverage và semantic review.
- Modify: `src/anime_review_mvp/render.py` — đo riêng duration stream video/audio và fail khi drift quá 80 ms.
- Modify: `src/anime_review_mvp/workflow.py` — thêm stage Codex và kết thúc sau audit, bỏ điều kiện đóng gói.
- Modify: `src/anime_review_mvp/workspace.py` — cho phép revision an toàn và xuất bản candidate sau PASS.
- Modify: `src/anime_review_mvp/cli.py` — nối luồng Antigravity nháp → Codex khóa → TTS → EDL → render → audit.
- Modify: `Bo_nao_Antigravity/GEMINI.md` — Antigravity dừng sau bản nháp và không chạm artifact Codex.
- Modify: `Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md` — prompt bàn giao đúng vai trò mới.
- Modify: `README.md` — hướng dẫn một tập theo phương án B, không package.
- Modify: `tests/fixtures/operator_artifacts/*` và các test liên quan — hợp đồng fixture mới.

---

### Task 1: Hợp đồng artifact khóa câu–cảnh của Codex

**Files:**
- Modify: `src/anime_review_mvp/models.py:136-281`
- Modify: `src/anime_review_mvp/antigravity.py:21-98`
- Create: `src/anime_review_mvp/editorial.py`
- Test: `tests/unit/test_models.py`
- Test: `tests/unit/test_antigravity_contract.py`
- Create: `tests/unit/test_editorial.py`

**Interfaces:**
- Produces: `SpanSourceRange`, `NarrationSpan`, `NarrationSpanDocument`, `load_locked_spans(path, truth, source_duration_ms) -> NarrationSpanDocument`.
- Consumes: `TruthDocument`, `Claim`, strict `jsonio.load_json` behavior.

- [ ] **Step 1: Viết test thất bại cho span nguyên tử và quyền sở hữu Codex**

```python
def test_locked_span_requires_one_sentence_and_visible_action(tmp_path: Path) -> None:
    payload = _locked_span_payload()
    payload["spans"][0]["text"] = "Jiro lao tới. Cậu tung cú đấm."
    payload["spans"][0]["visible_action"] = ""
    with pytest.raises(MvpError, match="one sentence|visible_action"):
        load_locked_spans(_write(tmp_path / "khoa_cau_canh.json", payload), _truth(), 10_000)


def test_operator_job_marks_codex_artifact_read_only(tmp_path: Path) -> None:
    job_path = build_operator_job(paths, source, transcript, shots)
    payload = json.loads(job_path.read_text(encoding="utf-8"))
    assert "codex_locked_spans" not in payload["required_outputs"]
    assert (
        str(paths.script_dir / "khoa_cau_canh.json") in payload["write_policy"]["read_only_roots"]
    )
```

- [ ] **Step 2: Chạy test và xác nhận thất bại vì chưa có model/loader**

Run: `uv run pytest tests/unit/test_models.py tests/unit/test_antigravity_contract.py tests/unit/test_editorial.py -v`

Expected: FAIL vì `NarrationSpan`, `SpanSourceRange` và `load_locked_spans` chưa tồn tại.

- [ ] **Step 3: Thêm model và loader tối thiểu**

```python
@dataclass(frozen=True, slots=True)
class SpanSourceRange:
    range_id: str
    source_start_ms: int
    source_end_ms: int
    scene_id: str
    beat_id: str
    shot_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    short_action_exception: bool = False


@dataclass(frozen=True, slots=True)
class NarrationSpan:
    span_id: str
    text: str
    claim_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    characters: tuple[str, ...]
    visible_action: str
    source_ranges: tuple[SpanSourceRange, ...]


@dataclass(frozen=True, slots=True)
class NarrationSpanDocument:
    spans: tuple[NarrationSpan, ...]
    claims: tuple[Claim, ...]
    owner: str
```

`load_locked_spans` phải yêu cầu `owner == "CODEX"`, ID duy nhất, đúng một câu kết thúc bằng `.`, `!` hoặc `?`, text/visible_action không rỗng, claim/event tồn tại trong truth, source range nằm trong nguồn và không chạm vùng `EXCLUDE`.

- [ ] **Step 4: Chạy test hợp đồng và ruff**

Run: `uv run pytest tests/unit/test_models.py tests/unit/test_antigravity_contract.py tests/unit/test_editorial.py -v`

Expected: PASS.

Run: `uv run ruff check src/anime_review_mvp/models.py src/anime_review_mvp/antigravity.py src/anime_review_mvp/editorial.py tests/unit/test_editorial.py`

Expected: PASS.

- [ ] **Step 5: Commit hợp đồng span**

```powershell
git add src/anime_review_mvp/models.py src/anime_review_mvp/antigravity.py src/anime_review_mvp/editorial.py tests/unit/test_models.py tests/unit/test_antigravity_contract.py tests/unit/test_editorial.py
git commit -m "feat: add Codex-owned narration span contract"
```

### Task 2: Ảnh neo đầu–giữa–cuối có manifest xác định

**Files:**
- Modify: `src/anime_review_mvp/models.py:80-120`
- Modify: `src/anime_review_mvp/media.py:171-200`
- Test: `tests/unit/test_media.py`
- Test: `tests/integration/test_media_ffmpeg.py`

**Interfaces:**
- Consumes: `NarrationSpanDocument`, `SpanSourceRange`, source MP4 hoặc final MP4.
- Produces: `FrameAnchor`, `FrameAnchorDocument`, `extract_span_anchors(video, spans, output_dir, timeline) -> FrameAnchorDocument`.

- [ ] **Step 1: Viết test thất bại cho ba ảnh mỗi span**

```python
def test_extract_span_anchors_requests_start_middle_and_end(tmp_path: Path) -> None:
    runner = FakeRunner()
    document = extract_span_anchors(
        tmp_path / "episode.mp4",
        _locked_spans(
            SpanSourceRange(
                "range-001", 1_000, 4_000, "scene-001", "beat-001", ("shot-1",), ("event-1",)
            )
        ),
        tmp_path / "anchors",
        timeline="SOURCE",
        runner=runner,
    )
    assert [anchor.position for anchor in document.anchors] == ["START", "MIDDLE", "END"]
    assert [anchor.timestamp_ms for anchor in document.anchors] == [1_080, 2_500, 3_920]
```

- [ ] **Step 2: Chạy test và xác nhận thất bại**

Run: `uv run pytest tests/unit/test_media.py::test_extract_span_anchors_requests_start_middle_and_end -v`

Expected: FAIL vì `extract_span_anchors` chưa tồn tại.

- [ ] **Step 3: Thêm model anchor và hàm trích frame**

```python
@dataclass(frozen=True, slots=True)
class FrameAnchor:
    anchor_id: str
    span_id: str
    range_id: str
    timeline: str
    position: str
    timestamp_ms: int
    path: str


@dataclass(frozen=True, slots=True)
class FrameAnchorDocument:
    anchors: tuple[FrameAnchor, ...]
```

Dùng lề an toàn 80 ms: `start + 80`, midpoint, `end - 80`; với range ngắn hơn 240 ms dùng ba mốc chia đều. Ghi `anchors.json` bằng `dump_json`. Không thay detector hiện có và không thêm dependency ngoài.

- [ ] **Step 4: Chạy unit/integration test media**

Run: `uv run pytest tests/unit/test_media.py tests/integration/test_media_ffmpeg.py -v`

Expected: PASS.

- [ ] **Step 5: Commit ảnh neo**

```powershell
git add src/anime_review_mvp/models.py src/anime_review_mvp/media.py tests/unit/test_media.py tests/integration/test_media_ffmpeg.py
git commit -m "feat: extract deterministic span anchor frames"
```

### Task 3: TTS theo span và EDL không cắt cơ học

**Files:**
- Modify: `src/anime_review_mvp/models.py:232-266`
- Modify: `src/anime_review_mvp/tts.py:284-322`
- Create: `src/anime_review_mvp/edl.py`
- Modify: `src/anime_review_mvp/validation.py:391-616`
- Test: `tests/unit/test_tts.py`
- Create: `tests/unit/test_edl.py`
- Modify: `tests/unit/test_validation.py`

**Interfaces:**
- Consumes: `NarrationSpanDocument` và WAV duration đo thật.
- Produces: `TtsSpan`, `TtsManifest.spans`, `build_edl_from_locked_spans(spans, tts, tolerance_ms=80, minimum_segment_ms=500) -> EdlDocument`.

- [ ] **Step 1: Viết test thất bại cho một WAV/một span và micro-clip**

```python
def test_tts_manifest_uses_span_ids(tmp_path: Path) -> None:
    manifest = synthesize_spans(
        _locked_spans(), tmp_path, provider=FakeProvider(), converter=_fake_converter
    )
    assert [item.span_id for item in manifest.spans] == ["span-001"]
    assert Path(manifest.spans[0].wav_path).name == "span-001.wav"


def test_edl_rejects_unapproved_micro_clip() -> None:
    spans = _locked_spans(range_duration_ms=300, short_action_exception=False)
    with pytest.raises(MvpError, match="500 ms"):
        build_edl_from_locked_spans(spans, _tts_spans([300]))


def test_edl_never_trims_source_range_to_fit_tts() -> None:
    spans = _locked_spans(range_duration_ms=2_000)
    with pytest.raises(MvpError, match="differs from TTS"):
        build_edl_from_locked_spans(spans, _tts_spans([1_500]))
```

- [ ] **Step 2: Chạy test và xác nhận thất bại**

Run: `uv run pytest tests/unit/test_tts.py tests/unit/test_edl.py tests/unit/test_validation.py -v`

Expected: FAIL vì TTS/EDL còn dùng cue và đang trim cuối OPTIONAL.

- [ ] **Step 3: Đổi TTS và EDL sang span**

```python
@dataclass(frozen=True, slots=True)
class TtsSpan:
    span_id: str
    mp3_path: str
    wav_path: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class EdlSegment:
    segment_id: str
    span_id: str
    source_start_ms: int
    source_end_ms: int
    program_start_ms: int
    program_end_ms: int
    range_id: str
    scene_id: str
    beat_id: str
    shot_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    short_action_exception: bool


def build_edl_from_locked_spans(
    document: NarrationSpanDocument,
    tts: TtsManifest,
    *,
    tolerance_ms: int = 80,
    minimum_segment_ms: int = 500,
) -> EdlDocument:
    durations = {item.span_id: item.duration_ms for item in tts.spans}
    if set(durations) != {span.span_id for span in document.spans}:
        raise MvpError("locked spans and TTS span IDs must match")
    segments: list[EdlSegment] = []
    cursor = 0
    used_ranges: list[tuple[int, int]] = []
    for span in document.spans:
        footage_ms = sum(item.source_end_ms - item.source_start_ms for item in span.source_ranges)
        if abs(footage_ms - durations[span.span_id]) > tolerance_ms:
            raise MvpError(f"locked footage differs from TTS for {span.span_id}")
        for index, item in enumerate(span.source_ranges, start=1):
            duration_ms = item.source_end_ms - item.source_start_ms
            if duration_ms < minimum_segment_ms and not item.short_action_exception:
                raise MvpError(f"EDL segment must be at least {minimum_segment_ms} ms")
            if any(
                item.source_start_ms < end and start < item.source_end_ms
                for start, end in used_ranges
            ):
                raise MvpError("locked EDL reuses source footage")
            used_ranges.append((item.source_start_ms, item.source_end_ms))
            segments.append(
                EdlSegment(
                    f"{span.span_id}-segment-{index:03d}",
                    span.span_id,
                    item.source_start_ms,
                    item.source_end_ms,
                    cursor,
                    cursor + duration_ms,
                    item.range_id,
                    item.scene_id,
                    item.beat_id,
                    item.shot_ids,
                    item.event_ids,
                    item.short_action_exception,
                )
            )
            cursor += duration_ms
    return EdlDocument(tuple(segments))
```

Hàm phải giữ nguyên mọi `source_start_ms/source_end_ms` do Codex chọn, nối program timing liên tục, cấm overlap/reuse nguồn, cấm segment dưới 500 ms nếu không có `short_action_exception`, và fail khi tổng range của span lệch WAV quá 80 ms. Xóa đường sử dụng `build_edl_from_scene_packets` khỏi CLI; không để compatibility fallback.

- [ ] **Step 4: Chạy test TTS/EDL/validation**

Run: `uv run pytest tests/unit/test_tts.py tests/unit/test_edl.py tests/unit/test_validation.py -v`

Expected: PASS.

- [ ] **Step 5: Commit TTS và EDL khóa span**

```powershell
git add src/anime_review_mvp/models.py src/anime_review_mvp/tts.py src/anime_review_mvp/edl.py src/anime_review_mvp/validation.py tests/unit/test_tts.py tests/unit/test_edl.py tests/unit/test_validation.py
git commit -m "feat: lock TTS and EDL to editorial spans"
```

### Task 4: Render fail-closed với drift stream tối đa 80 ms

**Files:**
- Modify: `src/anime_review_mvp/render.py:16-138`
- Test: `tests/unit/test_render.py`
- Modify: `tests/integration/test_render_ffmpeg.py`

**Interfaces:**
- Consumes: `EdlDocument`, narration WAV.
- Produces: `RenderResult` với `video_duration_ms`, `audio_duration_ms`, `drift_ms`; `probe_render(output: Path, *, allow_short_fixture: bool = False, max_av_drift_ms: int = 80, runner: Runner = subprocess.run) -> RenderResult`.

- [ ] **Step 1: Viết test thất bại cho duration từng stream và bỏ `-shortest`**

```python
def test_render_command_does_not_hide_drift_with_shortest() -> None:
    command = build_render_command(Path("source.mp4"), Path("voice.wav"), _edl(), Path("out.mp4"))
    assert "-shortest" not in command


def test_probe_render_rejects_stream_drift_over_80_ms(tmp_path: Path) -> None:
    runner = FakeRunner(stdout=_probe_payload(video_duration="8.000", audio_duration="8.081"))
    with pytest.raises(MvpError, match="80 ms"):
        probe_render(tmp_path / "out.mp4", allow_short_fixture=True, runner=runner)
```

- [ ] **Step 2: Chạy test và xác nhận thất bại**

Run: `uv run pytest tests/unit/test_render.py tests/integration/test_render_ffmpeg.py -v`

Expected: FAIL vì render dùng `-shortest` và chỉ đọc duration container.

- [ ] **Step 3: Đo duration của từng stream và fail khi lệch**

```python
@dataclass(frozen=True, slots=True)
class RenderResult:
    path: str
    duration_ms: int
    video_duration_ms: int
    audio_duration_ms: int
    drift_ms: int
    video_stream_count: int
    audio_stream_count: int
```

Đọc `duration` từ đúng video/audio stream của ffprobe, fallback sang `format.duration` chỉ khi cả hai stream thiếu duration và khi đó fail production audit với `STREAM_DURATION_UNAVAILABLE`. Bỏ `-shortest`; sau render, drift lớn hơn 80 ms là lỗi buộc Codex sửa span/TTS.

- [ ] **Step 4: Chạy render test**

Run: `uv run pytest tests/unit/test_render.py tests/integration/test_render_ffmpeg.py -v`

Expected: PASS.

- [ ] **Step 5: Commit render fail-closed**

```powershell
git add src/anime_review_mvp/render.py tests/unit/test_render.py tests/integration/test_render_ffmpeg.py
git commit -m "fix: fail renders with hidden audio video drift"
```

### Task 5: Semantic review của Codex và PASS do engine tính

**Files:**
- Modify: `src/anime_review_mvp/models.py:268-281`
- Create: `src/anime_review_mvp/audit.py`
- Modify: `src/anime_review_mvp/validation.py:619-633`
- Test: `tests/unit/test_audit.py`
- Modify: `tests/unit/test_validation.py`

**Interfaces:**
- Consumes: `NarrationSpanDocument`, `TtsManifest`, source/final `FrameAnchorDocument`, `CodexSemanticReview` không có trường `passed`.
- Produces: `EngineAuditReport`; `build_engine_audit(spans: NarrationSpanDocument, tts: TtsManifest, review: CodexSemanticReview, source_anchors: FrameAnchorDocument, final_anchors: FrameAnchorDocument, render: RenderResult) -> EngineAuditReport`, coverage do duration WAV thật tính.

- [ ] **Step 1: Viết test thất bại chống self-PASS**

```python
def test_semantic_review_schema_has_no_passed_field(tmp_path: Path) -> None:
    payload = _semantic_review_payload()
    payload["passed"] = True
    with pytest.raises(MvpError, match="artifact contract"):
        load_json(_write(tmp_path / "codex_review.json", payload), CodexSemanticReview)


def test_engine_audit_weights_verified_spans_by_tts_duration() -> None:
    report = build_engine_audit(
        _locked_spans(2),
        _tts_spans([8_000, 2_000]),
        _semantic_review([True, False]),
        _source_anchors(2),
        _final_anchors(2),
        _render_result(drift_ms=0),
    )
    assert report.coverage_ratio == "0.8"
    assert report.passed is True
```

- [ ] **Step 2: Chạy test và xác nhận thất bại**

Run: `uv run pytest tests/unit/test_audit.py tests/unit/test_validation.py -v`

Expected: FAIL vì audit hiện tin `AuditReport.passed` của Antigravity.

- [ ] **Step 3: Thêm schema review không có PASS và engine audit**

```python
@dataclass(frozen=True, slots=True)
class SpanSemanticReview:
    span_id: str
    supported: bool
    finding_codes: tuple[str, ...]
    evidence_anchor_ids: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class CodexSemanticReview:
    owner: str
    spans: tuple[SpanSemanticReview, ...]


@dataclass(frozen=True, slots=True)
class EngineAuditReport:
    passed: bool
    coverage_ratio: str
    findings: tuple[AuditFinding, ...]
```

`build_engine_audit` phải yêu cầu `owner == "CODEX"`, review đủ mọi span, mỗi review có anchor nguồn và anchor thành phẩm thuộc đúng span, không có code chặn, coverage >= 0.80, drift <= 80 ms, duration 420–720 giây và đúng một video/một audio. Engine tự đặt `passed`; không nhận trường này từ input.

- [ ] **Step 4: Chạy audit test**

Run: `uv run pytest tests/unit/test_audit.py tests/unit/test_validation.py -v`

Expected: PASS.

- [ ] **Step 5: Commit independent audit**

```powershell
git add src/anime_review_mvp/models.py src/anime_review_mvp/audit.py src/anime_review_mvp/validation.py tests/unit/test_audit.py tests/unit/test_validation.py
git commit -m "feat: compute final audit from Codex evidence"
```

### Task 6: Nối workflow lai và loại package khỏi đường chạy đạt

**Files:**
- Modify: `src/anime_review_mvp/workflow.py:11-150`
- Modify: `src/anime_review_mvp/cli.py:43-340`
- Modify: `src/anime_review_mvp/antigravity.py:21-98`
- Modify: `src/anime_review_mvp/workspace.py:49-103`
- Modify: `tests/unit/test_workflow.py`
- Modify: `tests/unit/test_cli.py`
- Modify: `tests/acceptance/test_episode_pipeline.py`
- Modify: `tests/fixtures/operator_artifacts/kich_ban_review.json`
- Create: `tests/fixtures/operator_artifacts/khoa_cau_canh.json`
- Create: `tests/fixtures/operator_artifacts/codex_semantic_review.json`

**Interfaces:**
- Consumes: các interfaces từ Task 1–5.
- Produces: CLI `lock`, `tts`, `render`, `audit --phase video --codex-review PATH` và stage `CODEX_BIEN_TAP`; audit đạt chuyển thẳng `HOAN_THANH` mà không xóa run.

- [ ] **Step 1: Viết workflow/acceptance test thất bại**

```python
def test_antigravity_draft_stops_for_codex_editor(tmp_path: Path) -> None:
    run = _prepared_run(tmp_path, stage=Stage.KIEM_DINH_KICH_BAN)
    assert main(["audit", "--run", str(run), "--phase", "script"]) == 0
    assert read_state(run).stage is Stage.CODEX_BIEN_TAP
    assert "Codex" in (run / "next_action.json").read_text(encoding="utf-8")


def test_final_audit_completes_without_package_or_cleanup(tmp_path: Path) -> None:
    run, episode = _rendered_fixture(tmp_path)
    review = episode / "Bao_cao_Codex" / "codex_semantic_review.json"
    assert (
        main(["audit", "--run", str(run), "--phase", "video", "--codex-review", str(review)]) == 0
    )
    assert read_state(run).stage is Stage.HOAN_THANH
    assert run.exists()
    assert not (tmp_path / "Goi_gui_ChatGPT_Web").exists()


def test_revision_keeps_current_final_until_candidate_passes(tmp_path: Path) -> None:
    run, episode = _revision_fixture(tmp_path, current_final=b"old")
    main(["render", "--run", str(run)])
    assert (episode / "Thanh_pham" / "review_anime.mp4").read_bytes() == b"old"
    assert (run / "review_candidate.mp4").is_file()
```

- [ ] **Step 2: Chạy workflow/CLI/acceptance test và xác nhận thất bại**

Run: `uv run pytest tests/unit/test_workflow.py tests/unit/test_cli.py tests/acceptance/test_episode_pipeline.py -v`

Expected: FAIL vì chưa có `CODEX_BIEN_TAP`, lệnh `lock` và audit vẫn chuyển sang `DONG_GOI`.

- [ ] **Step 3: Nối state và CLI mới**

```python
class Stage(StrEnum):
    CHUAN_BI = "CHUAN_BI"
    QUAN_SAT = "QUAN_SAT"
    VIET_KICH_BAN = "VIET_KICH_BAN"
    KIEM_DINH_KICH_BAN = "KIEM_DINH_KICH_BAN"
    CODEX_BIEN_TAP = "CODEX_BIEN_TAP"
    TAO_TTS = "TAO_TTS"
    LAP_EDL = "LAP_EDL"
    DUNG_VIDEO = "DUNG_VIDEO"
    KIEM_DINH_VIDEO = "KIEM_DINH_VIDEO"
    HOAN_THANH = "HOAN_THANH"
```

`start --revision` cho phép tạo run mới khi đã có thành phẩm nhưng không ghi đè nó. `audit --phase script` chỉ kiểm tra bản nháp rồi chuyển `CODEX_BIEN_TAP`. `lock` load `khoa_cau_canh.json`, validate và trích anchor nguồn rồi chuyển `TAO_TTS`. `tts` dùng span và tạo EDL khóa. `render` ghi `review_candidate.mp4`, `render_result.json` và anchor thành phẩm trong run. `audit --phase video` load review Codex, tự sinh `kiem_dinh_engine.json`; khi đạt, nó lưu thành phẩm cũ vào `Bao_cao/phien_ban_cu`, dùng `os.replace` xuất bản candidate, rồi chuyển thẳng `HOAN_THANH`. Không gọi `finalize_run` và không dọn run.

- [ ] **Step 4: Chạy acceptance path mới**

Run: `uv run pytest tests/unit/test_workflow.py tests/unit/test_cli.py tests/acceptance/test_episode_pipeline.py -v`

Expected: PASS; fixture đạt `HOAN_THANH`, MP4/run còn nguyên, không có ZIP.

- [ ] **Step 5: Commit workflow lai**

```powershell
git add src/anime_review_mvp/workflow.py src/anime_review_mvp/cli.py src/anime_review_mvp/antigravity.py src/anime_review_mvp/workspace.py tests/unit/test_workflow.py tests/unit/test_cli.py tests/acceptance/test_episode_pipeline.py tests/fixtures/operator_artifacts
git commit -m "feat: route episodes through Codex editorial approval"
```

### Task 7: Khóa hướng dẫn Antigravity và tài liệu vận hành

**Files:**
- Modify: `Bo_nao_Antigravity/GEMINI.md`
- Modify: `Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md`
- Modify: `README.md`
- Modify: `tests/unit/test_antigravity_contract.py`

**Interfaces:**
- Consumes: CLI/stage hoàn chỉnh từ Task 6.
- Produces: prompt một lần chạy để Antigravity chỉ giao bản nháp có bằng chứng và dừng đúng điểm Codex tiếp quản.

- [ ] **Step 1: Viết contract test thất bại cho văn bản điều khiển**

```python
def test_antigravity_brain_stops_before_codex_owned_steps() -> None:
    brain = Path("Bo_nao_Antigravity/GEMINI.md").read_text(encoding="utf-8")
    prompt = Path("Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md").read_text(encoding="utf-8")
    for text in (brain, prompt):
        assert "CODEX_BIEN_TAP" in text
        assert "không chạy lock" in text
        assert "không tạo khoa_cau_canh.json" in text
        assert "không tự cấp PASS" in text
```

- [ ] **Step 2: Chạy test và xác nhận thất bại**

Run: `uv run pytest tests/unit/test_antigravity_contract.py::test_antigravity_brain_stops_before_codex_owned_steps -v`

Expected: FAIL vì prompt hiện yêu cầu Antigravity tự TTS/render/audit.

- [ ] **Step 3: Sửa hướng dẫn đúng phân vai đã duyệt**

Luồng ghi trong cả ba tài liệu phải là:

```text
Antigravity: prepare → truth → scene_packets → lời nháp → audit script → DỪNG Ở CODEX_BIEN_TAP
Codex: kiểm tra frame → khoa_cau_canh.json → lock → TTS → EDL → render → semantic review → engine audit
```

Xóa mọi chỉ dẫn tích cực yêu cầu Antigravity chạy `tts`, `render`, `audit --phase video` hoặc `package`. Nêu rõ nó không được tạo/sửa `khoa_cau_canh.json`, `codex_semantic_review.json`, `kiem_dinh_engine.json` và không được tự báo video đạt.

- [ ] **Step 4: Chạy test tài liệu và tìm chỉ dẫn cũ**

Run: `uv run pytest tests/unit/test_antigravity_contract.py -v`

Expected: PASS.

Run: `rg -n "Antigravity.*(TTS|render|package)|→ TTS|→ render|chạy package" Bo_nao_Antigravity README.md`

Expected: không còn chỉ dẫn vận hành trái phương án B.

- [ ] **Step 5: Commit tài liệu vận hành**

```powershell
git add Bo_nao_Antigravity/GEMINI.md Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md README.md tests/unit/test_antigravity_contract.py
git commit -m "docs: hand final editing from Antigravity to Codex"
```

### Task 8: Kiểm định toàn bộ và dựng lại BLACK TORCH tập 1

**Files:**
- Modify: `Kho_Anime/BLACK TORCH/Mua_01/Tap_001/Kich_ban/khoa_cau_canh.json`
- Create: `Kho_Anime/BLACK TORCH/Mua_01/Tap_001/Bao_cao_Codex/codex_semantic_review.json`
- Regenerate: `Kho_Anime/BLACK TORCH/Mua_01/Tap_001/TTS/*`
- Regenerate: `Kho_Anime/BLACK TORCH/Mua_01/Tap_001/Ke_hoach_canh/edl.json`
- Regenerate: `Kho_Anime/BLACK TORCH/Mua_01/Tap_001/Thanh_pham/review_anime.mp4`
- Create: `Kho_Anime/BLACK TORCH/Mua_01/Tap_001/Bao_cao/kiem_dinh_engine.json`

**Interfaces:**
- Consumes: pipeline hoàn chỉnh Task 1–7 và video nguồn `D:/Tóm tắt anime/video/Watch BLACK TORCH Episode 1 Online Free _ Enma.mp4`.
- Produces: MP4 TTS-only 7–12 phút cùng audit engine và bằng chứng frame từng span.

- [ ] **Step 1: Chạy toàn bộ test và lint trước dữ liệu thật**

Run: `uv run pytest -v`

Expected: toàn bộ test PASS.

Run: `uv run ruff check .`

Expected: PASS.

Run: `git diff --check`

Expected: không có whitespace error.

- [ ] **Step 2: Tạo revision run mới nhưng giữ nguyên thành phẩm hiện tại**

Run:

```powershell
$sourceVideo = 'D:\Tóm tắt anime\video\Watch BLACK TORCH Episode 1 Online Free _ Enma.mp4'
$runDir = (uv run python run_episode.py start --anime 'BLACK TORCH' --season 1 --episode 1 --video $sourceVideo --revision | Select-Object -Last 1).Trim()
$runDir
```

Expected: tạo run mới ở `CHUAN_BI`; thành phẩm tệ hiện tại vẫn nằm nguyên tại `Thanh_pham/review_anime.mp4`.

- [ ] **Step 3: Prepare và giao đúng prompt cho Antigravity tạo bản nháp**

Run: `uv run python run_episode.py prepare --run $runDir`

Expected: job chứa transcript/shot/frame và `next_action.json` yêu cầu Antigravity tạo truth, scene packets và lời nháp rồi dừng ở `CODEX_BIEN_TAP`. Người dùng gửi prompt cho Antigravity và chuyển báo cáo về; Codex không tự điều khiển Antigravity.

- [ ] **Step 4: Codex xem frame nguồn và viết khóa span cuối**

Codex phải dùng transcript, truth, scene packets và frame nguồn để viết `khoa_cau_canh.json`. Mỗi span có một câu, một visible_action, range liên tục tối thiểu 500 ms hoặc ngoại lệ hành động có giải thích. Không tái sử dụng range nguồn và không dùng OP/ED.

- [ ] **Step 5: Chạy lock, TTS, EDL và render candidate**

Run:

```powershell
uv run python run_episode.py lock --run $runDir
uv run python run_episode.py tts --run $runDir
uv run python run_episode.py validate --run $runDir --artifact edl
uv run python run_episode.py render --run $runDir
```

Expected: mỗi lệnh exit 0; `review_candidate.mp4` nằm trong run, video/audio drift <= 80 ms, không có segment không được phép dưới 500 ms và thành phẩm cũ chưa bị thay.

- [ ] **Step 6: Codex xem ảnh đầu–giữa–cuối trên candidate và lập semantic review**

Mỗi span phải có ba anchor thành phẩm. Span sai người, sai hành động, nói trước/sau hình hoặc văn yếu được đặt `supported=false`, sửa đúng span rồi tạo lại TTS/EDL/render. Không đặt tất cả span PASS bằng thao tác hàng loạt.

- [ ] **Step 7: Chạy engine audit cuối và xuất bản an toàn**

Run:

```powershell
$codexReview = 'D:\FINAL REVIEW ANIME\Kho_Anime\BLACK TORCH\Mua_01\Tap_001\Bao_cao_Codex\codex_semantic_review.json'
uv run python run_episode.py audit --run $runDir --phase video --codex-review $codexReview
```

Expected: exit 0, state `HOAN_THANH`, coverage >= 0.80, duration 420–720 giây, drift <= 80 ms, đúng một video và một audio TTS tiếng Việt; bản cũ được lưu trong `Bao_cao/phien_ban_cu`, candidate mới trở thành `Thanh_pham/review_anime.mp4`.

- [ ] **Step 8: Kiểm tra media độc lập và giao cho người dùng xem**

Run:

```powershell
ffprobe -v error -show_streams -show_format -of json 'D:\FINAL REVIEW ANIME\Kho_Anime\BLACK TORCH\Mua_01\Tap_001\Thanh_pham\review_anime.mp4'
```

Expected: H.264 video, một audio AAC TTS, không audio nguồn, duration 7–12 phút. Báo đường dẫn MP4 và audit; không ZIP, không dọn run và không tự khẳng định “hoàn hảo” trước khi người dùng xem.

- [ ] **Step 9: Commit mã nguồn và tài liệu, không commit video/artifact lớn**

```powershell
git status --short
git add src tests Bo_nao_Antigravity README.md pyproject.toml uv.lock
git commit -m "feat: enforce Codex scene voice lock"
```

Expected: commit chỉ chứa mã nguồn/test/docs cần thiết; `Kho_Anime`, TTS, MP4 và run không nằm trong commit.
