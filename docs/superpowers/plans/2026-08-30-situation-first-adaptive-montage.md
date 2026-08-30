# Situation-First Adaptive Montage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, situation-first anime review pipeline that derives story units from transcript/SRT plus frames, enforces adaptive keep/skip editing, locks narration/TTS/footage one situation at a time, and removes Gemini Web from the default workflow.

**Architecture:** A local evidence extractor produces timestamped transcript, shots, and frame packets; a local editor agent writes structured `SituationDocument` and `NarrationPlan` artifacts; deterministic validators, TTS, adaptive EDL, render, fingerprint, and workflow modules enforce every measurable rule. Gemini browser code remains available only behind an explicit optional audit command and cannot advance or repair the default run.

**Tech Stack:** Python 3.12 dataclasses, pytest, FFmpeg/FFprobe, existing Whisper integration, Pillow, existing TikTok/CapCut TTS provider, JSON artifacts.

**Spec:** `docs/superpowers/specs/2026-08-30-situation-first-adaptive-montage-design.md`

## Global Constraints

- Do not install dependencies automatically; preflight must stop and name each missing executable or Python package.
- Do not hard-code anime names, episode numbers, or BLACK TORCH timestamps in engine modules.
- No fixed keep duration, skip duration, or keep/skip ratio.
- Every kept source range must be followed by a real omitted source interval of at least `500 ms`; for the final kept range, the remaining source tail is the omitted interval.
- Reject kept clips shorter than `500 ms`, black/flash/transition edge frames, and source ranges intersecting confirmed excluded regions.
- Clip playback rate defaults to the inclusive range `0.80x–1.30x`; never time-stretch or pitch-shift TTS to repair timing.
- Gemini Web is not part of the default state machine and cannot write a local validator PASS.
- Two consecutive repairs with the same content fingerprint and finding codes stop with `KHONG_CO_TIEN_TRIEN`.
- Preserve source video and unrelated dirty-worktree changes.
- Use TDD for every behavior and commit only the files belonging to each task.

---

## File Structure

- Create `src/anime_review_mvp/situations.py`: situation, evidence, narration, and editorial-policy dataclasses plus strict JSON loaders.
- Create `src/anime_review_mvp/situation_validation.py`: source-region, situation, keep/skip, claim-evidence, ordering, and style validators.
- Create `src/anime_review_mvp/situation_packets.py`: local editor-agent packet and prompt generation from transcript, shots, frames, and prior context.
- Create `src/anime_review_mvp/adaptive_edl.py`: TTS-duration-aware playback-rate calculation and adaptive EDL construction.
- Create `src/anime_review_mvp/local_audit.py`: deterministic audit aggregation and semantic-review contract validation.
- Modify `src/anime_review_mvp/media.py`: preflight and frame-quality/motion evidence extraction.
- Modify `src/anime_review_mvp/render.py`: render adaptive EDL segments with per-unit video speed.
- Modify `src/anime_review_mvp/tts.py`: synthesize/cache narration by situation unit.
- Modify `src/anime_review_mvp/workflow.py`: local-first stages, per-situation progress, fingerprints, and no-progress stop.
- Modify `src/anime_review_mvp/cli.py`: expose local prepare/validate/TTS/render/audit flow and optional Gemini audit only.
- Modify `src/anime_review_mvp/antigravity.py` and `Bo_nao_Antigravity/GEMINI.md`: restrict the operator to structured local artifacts and sequential situation locking.
- Add focused unit tests under `tests/unit/` and one FFmpeg integration test under `tests/integration/`.

### Task 1: Define the Situation-First Data Contracts and Policy

**Files:**
- Create: `src/anime_review_mvp/situations.py`
- Test: `tests/unit/test_situations.py`

**Interfaces:**
- Produces: `EditorialPolicy`, `Situation`, `SituationDocument`, `EvidenceRange`, `NarrationUnit`, `NarrationPlan`, `SituationTts`, `SituationTtsManifest`, `SemanticUnitReview`, `SemanticReviewDocument`, `load_situations(path)`, and `load_narration_plan(path)`.
- Consumes: `MvpError` from `src/anime_review_mvp/errors.py` and `load_json` from `src/anime_review_mvp/jsonio.py`.

- [ ] **Step 1: Write failing constructor and JSON-loading tests**

```python
def test_policy_rejects_fixed_keep_skip_formula() -> None:
    with pytest.raises(MvpError, match="fixed keep/skip"):
        EditorialPolicy(fixed_keep_ms=6_000, fixed_skip_ms=4_000)


def test_situation_requires_transcript_and_frame_evidence() -> None:
    with pytest.raises(MvpError, match="transcript and frame"):
        Situation(
            situation_id="situation-001", source_start_ms=10_000,
            source_end_ms=60_000, story_role="MAIN_PLOT", characters=("Jiro",),
            setup="Jiro is surrounded.", new_information=("The gang attacks Jiro.",),
            turning_points=("Jiro fights back.",), outcome="Jiro wins.",
            transcript_refs=(), frame_refs=("frame-001",), previous_situation_id=None,
            next_situation_id=None, confidence=1.0,
        )
```

- [ ] **Step 2: Run the focused tests and verify the missing module failure**

Run: `uv run pytest tests/unit/test_situations.py -v`

Expected: FAIL during collection with `ModuleNotFoundError: anime_review_mvp.situations`.

- [ ] **Step 3: Implement immutable contracts with strict validation**

```python
@dataclass(frozen=True, slots=True)
class EditorialPolicy:
    minimum_clip_ms: int = 500
    minimum_omitted_gap_ms: int = 500
    minimum_playback_rate: float = 0.80
    maximum_playback_rate: float = 1.30
    forbidden_before_ms: int = 0
    target_minimum_ms: int = 420_000
    target_maximum_ms: int = 720_000
    fixed_keep_ms: int | None = None
    fixed_skip_ms: int | None = None

    def __post_init__(self) -> None:
        if self.fixed_keep_ms is not None or self.fixed_skip_ms is not None:
            raise MvpError("fixed keep/skip formulas are forbidden")
        if not 0 < self.minimum_playback_rate <= self.maximum_playback_rate:
            raise MvpError("playback-rate policy is invalid")


@dataclass(frozen=True, slots=True)
class EvidenceRange:
    range_id: str
    situation_id: str
    source_start_ms: int
    source_end_ms: int
    shot_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    transcript_refs: tuple[str, ...]
    frame_refs: tuple[str, ...]
    story_fact: str


@dataclass(frozen=True, slots=True)
class NarrationUnit:
    unit_id: str
    situation_id: str
    factual_claims: tuple[str, ...]
    narration_text: str
    bridge_from_previous: str
    bridge_to_next: str
    evidence_ranges: tuple[EvidenceRange, ...]
    status: str


@dataclass(frozen=True, slots=True)
class Situation:
    situation_id: str
    source_start_ms: int
    source_end_ms: int
    story_role: str
    characters: tuple[str, ...]
    setup: str
    new_information: tuple[str, ...]
    turning_points: tuple[str, ...]
    outcome: str
    transcript_refs: tuple[str, ...]
    frame_refs: tuple[str, ...]
    previous_situation_id: str | None
    next_situation_id: str | None
    confidence: float


@dataclass(frozen=True, slots=True)
class SituationDocument:
    owner: str
    policy_version: str
    situations: tuple[Situation, ...]


@dataclass(frozen=True, slots=True)
class NarrationPlan:
    owner: str
    policy_version: str
    units: tuple[NarrationUnit, ...]


@dataclass(frozen=True, slots=True)
class SituationTts:
    unit_id: str
    mp3_path: str
    wav_path: str
    duration_ms: int
    cache_key: str


@dataclass(frozen=True, slots=True)
class SituationTtsManifest:
    units: tuple[SituationTts, ...]
    narration_wav_path: str
    provider: str
    voice_id: str
    policy_version: str
    cache_hits: int
    cache_misses: int
    total_duration_ms: int


@dataclass(frozen=True, slots=True)
class SemanticUnitReview:
    unit_id: str
    supported: bool
    finding_codes: tuple[str, ...]
    transcript_refs: tuple[str, ...]
    source_frame_refs: tuple[str, ...]
    program_frame_refs: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class SemanticReviewDocument:
    owner: str
    units: tuple[SemanticUnitReview, ...]
```

Restrict `story_role` to `MAIN_PLOT | SUPPORTING_PLOT`, `status` to `DRAFT | LOCKED | NEEDS_REPAIR`, confidence to `[0, 1]`, TTS durations to positive integers, cache keys to lowercase SHA-256, and all required IDs/text/evidence collections to non-empty values. `SituationDocument.owner` and `NarrationPlan.owner` must be `LOCAL_EDITOR`; `SemanticReviewDocument.owner` must be `LOCAL_SEMANTIC_AUDITOR`.

- [ ] **Step 4: Add valid round-trip tests and run them**

Run: `uv run pytest tests/unit/test_situations.py -v`

Expected: PASS, including `load_situations()` and `load_narration_plan()` on strict JSON fixtures.

- [ ] **Step 5: Commit the contracts**

```powershell
git add src/anime_review_mvp/situations.py tests/unit/test_situations.py
git commit -m "feat: add situation-first editorial contracts"
```

### Task 2: Extract Local Evidence and Fail Clearly on Missing Tools

**Files:**
- Modify: `src/anime_review_mvp/media.py`
- Create: `tests/unit/test_media_evidence.py`
- Modify: `tests/unit/test_media.py`

**Interfaces:**
- Consumes: `TranscriptDocument`, `Shot`, and source video path.
- Produces: `preflight_media_tools(required=("ffmpeg", "ffprobe")) -> tuple[Path, ...]`, `evidence_timestamps(shots, transcript) -> tuple[int, ...]`, and `classify_edge_frame(path) -> str` where the classification is `CONTENT | BLACK | FLASH | TRANSITION`.

- [ ] **Step 1: Write failing preflight and timestamp tests**

```python
def test_preflight_names_every_missing_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(MvpError, match="ffmpeg, ffprobe"):
        preflight_media_tools()


def test_evidence_timestamps_include_subtitle_and_shot_boundaries() -> None:
    assert evidence_timestamps(SHOTS, TRANSCRIPT) == (0, 900, 1_000, 1_500, 2_000)
```

- [ ] **Step 2: Verify both tests fail before implementation**

Run: `uv run pytest tests/unit/test_media_evidence.py tests/unit/test_media.py -v`

Expected: FAIL because the new functions do not exist.

- [ ] **Step 3: Implement deterministic preflight and evidence sampling**

```python
def preflight_media_tools(required: tuple[str, ...] = ("ffmpeg", "ffprobe")) -> tuple[Path, ...]:
    missing = tuple(name for name in required if shutil.which(name) is None)
    if missing:
        raise MvpError(f"missing required tools: {', '.join(missing)}; install them and rerun")
    return tuple(Path(cast(str, shutil.which(name))) for name in required)


def evidence_timestamps(shots: tuple[Shot, ...], transcript: TranscriptDocument) -> tuple[int, ...]:
    values = {shot.start_ms for shot in shots} | {shot.end_ms for shot in shots}
    for segment in transcript.segments:
        values.update((segment.start_ms, (segment.start_ms + segment.end_ms) // 2, segment.end_ms))
    return tuple(sorted(value for value in values if value >= 0))
```

Use Pillow luminance mean and variance for `BLACK`/`FLASH`; label a frame `TRANSITION` only when adjacent-frame difference exceeds the configured threshold and the condition persists for less than `500 ms`. Keep thresholds module constants and cover them with generated black/white/content fixtures.

- [ ] **Step 4: Run media unit and existing integration tests**

Run: `uv run pytest tests/unit/test_media.py tests/unit/test_media_evidence.py tests/integration/test_media_ffmpeg.py -v`

Expected: PASS; if FFmpeg is unavailable, integration tests may skip, while preflight unit tests still pass.

- [ ] **Step 5: Commit evidence extraction**

```powershell
git add src/anime_review_mvp/media.py tests/unit/test_media.py tests/unit/test_media_evidence.py
git commit -m "feat: extract transcript and frame evidence locally"
```

### Task 3: Validate Situations, Excluded Regions, and Narrative Importance

**Files:**
- Create: `src/anime_review_mvp/situation_validation.py`
- Create: `tests/unit/test_situation_validation.py`

**Interfaces:**
- Consumes: `SituationDocument`, `NarrationPlan`, `TruthDocument`, `ShotDocument`, `EditorialPolicy`, and source duration.
- Produces: `validate_situations(...) -> None`, `validate_narration_plan(...) -> None`, and `validate_keep_skip(...) -> None`.

- [ ] **Step 1: Write failing validation tests for the user-visible rules**

```python
def test_rejects_action_without_new_story_information() -> None:
    document = situation_document(action_value="DECORATIVE", new_information=())
    with pytest.raises(MvpError, match="no review value"):
        validate_situations(document, TRUTH, SHOTS, source_duration_ms=120_000)


def test_rejects_kept_range_in_confirmed_opening() -> None:
    plan = narration_plan(range_start_ms=0, range_end_ms=4_000)
    with pytest.raises(MvpError, match="excluded source region"):
        validate_narration_plan(plan, SITUATIONS, TRUTH_WITH_OPENING, SHOTS, POLICY, 120_000)


def test_requires_real_omitted_gap_after_every_kept_range() -> None:
    plan = narration_plan_with_ranges((10_000, 14_000), (14_200, 20_000))
    with pytest.raises(MvpError, match="omitted gap.*500"):
        validate_keep_skip(plan, source_duration_ms=120_000, policy=POLICY)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/test_situation_validation.py -v`

Expected: FAIL because `situation_validation` does not exist.

- [ ] **Step 3: Implement strict ordered validation**

```python
def validate_keep_skip(plan: NarrationPlan, source_duration_ms: int, policy: EditorialPolicy) -> None:
    ranges = sorted(
        (item for unit in plan.units for item in unit.evidence_ranges),
        key=lambda item: item.source_start_ms,
    )
    for current, following in pairwise(ranges):
        gap_ms = following.source_start_ms - current.source_end_ms
        if gap_ms < policy.minimum_omitted_gap_ms:
            raise MvpError(f"omitted gap must be at least {policy.minimum_omitted_gap_ms} ms")
    tail_ms = source_duration_ms - ranges[-1].source_end_ms
    if tail_ms < policy.minimum_omitted_gap_ms:
        raise MvpError("final kept range requires an omitted source tail")
```

Also enforce: ranges follow situation/source order, ranges align to known shots, every claim has transcript or frame refs, every range starts at/after `forbidden_before_ms`, excluded regions never overlap, supporting situations without future setup/payoff are omitted, and `LOCKED` units contain both bridges except at program boundaries.

- [ ] **Step 4: Run focused and regression validation tests**

Run: `uv run pytest tests/unit/test_situation_validation.py tests/unit/test_validation.py tests/unit/test_editorial.py -v`

Expected: PASS without weakening existing source-region checks.

- [ ] **Step 5: Commit situation validation**

```powershell
git add src/anime_review_mvp/situation_validation.py tests/unit/test_situation_validation.py
git commit -m "feat: enforce story-value and adaptive keep-skip rules"
```

### Task 4: Generate the Local Situation-Editor Packet

**Files:**
- Create: `src/anime_review_mvp/situation_packets.py`
- Modify: `src/anime_review_mvp/antigravity.py`
- Modify: `Bo_nao_Antigravity/GEMINI.md`
- Create: `tests/unit/test_situation_packets.py`
- Modify: `tests/unit/test_antigravity_contract.py`

**Interfaces:**
- Consumes: source metadata, `TranscriptDocument`, `ShotDocument`, extracted frame manifest, prior-episode context, and `EditorialPolicy`.
- Produces: `build_situation_editor_packet(...) -> SituationEditorPacket` and `render_situation_editor_prompt(packet) -> str`.

- [ ] **Step 1: Write a failing packet-contract test**

```python
def test_packet_requires_transcript_frames_and_prior_context(tmp_path: Path) -> None:
    packet = build_situation_editor_packet(SOURCE, TRANSCRIPT, SHOTS, FRAMES, POLICY, None)
    prompt = render_situation_editor_prompt(packet)
    assert "MAIN_PLOT | SUPPORTING_PLOT" in prompt
    assert "không giữ hành động chỉ vì đẹp" in prompt
    assert "sau mỗi khoảng lấy phải có khoảng nguồn bị bỏ" in prompt
    assert "Gemini Web" not in prompt
```

- [ ] **Step 2: Run packet tests and confirm failure**

Run: `uv run pytest tests/unit/test_situation_packets.py tests/unit/test_antigravity_contract.py -v`

Expected: FAIL because the packet builder is missing and the old operator output contract still targets atomic storyboard/Gemini.

- [ ] **Step 3: Implement a bounded local-agent contract**

```python
@dataclass(frozen=True, slots=True)
class SituationEditorPacket:
    source: SourceRef
    transcript: TranscriptDocument
    shots: ShotDocument
    frame_manifest_path: str
    policy: EditorialPolicy
    prior_context: str
    required_outputs: tuple[str, ...] = ("situations.json", "narration_plan.json")
```

Update the operator instructions to process one situation at a time and write only run artifacts. Require this order: observe facts, assign main/supporting role, select informative evidence with real gaps, write colloquial Vietnamese, synthesize/lock the current unit, then proceed. Explicitly prohibit modifying source, `src`, `tests`, policy, `run_state.json`, or declaring technical PASS.

- [ ] **Step 4: Run contract tests**

Run: `uv run pytest tests/unit/test_situation_packets.py tests/unit/test_antigravity_contract.py -v`

Expected: PASS and prompt snapshots contain no default browser-review instruction.

- [ ] **Step 5: Commit the local editor packet**

```powershell
git add src/anime_review_mvp/situation_packets.py src/anime_review_mvp/antigravity.py Bo_nao_Antigravity/GEMINI.md tests/unit/test_situation_packets.py tests/unit/test_antigravity_contract.py
git commit -m "feat: define local situation editor workflow"
```

### Task 5: Build Adaptive EDL and Per-Unit Playback Rates

**Files:**
- Create: `src/anime_review_mvp/adaptive_edl.py`
- Modify: `src/anime_review_mvp/situations.py`
- Create: `tests/unit/test_adaptive_edl.py`

**Interfaces:**
- Consumes: `NarrationPlan`, `SituationTtsManifest`, source duration, and `EditorialPolicy`.
- Produces: `AdaptiveEdlSegment`, `AdaptiveEdlDocument`, `choose_playback_rate(footage_ms, voice_ms, policy) -> float`, and `build_adaptive_edl(...) -> AdaptiveEdlDocument`.

- [ ] **Step 1: Write failing rate, duration, and keep/skip tests**

```python
def test_voice_shorter_than_footage_uses_bounded_speedup() -> None:
    assert choose_playback_rate(3_000, 2_400, POLICY) == pytest.approx(1.25)


def test_rate_outside_policy_requests_narration_repair() -> None:
    with pytest.raises(MvpError, match="rewrite narration or select evidence"):
        choose_playback_rate(10_000, 2_000, POLICY)


def test_adaptive_edl_preserves_source_gap_and_matches_voice() -> None:
    edl = build_adaptive_edl(PLAN, TTS, source_duration_ms=60_000, policy=POLICY)
    assert edl.segments[0].playback_rate == pytest.approx(1.25)
    assert edl.segments[-1].program_end_ms == TTS.total_duration_ms
```

- [ ] **Step 2: Run the adaptive EDL tests and verify failure**

Run: `uv run pytest tests/unit/test_adaptive_edl.py -v`

Expected: FAIL because the adaptive EDL interfaces are absent.

- [ ] **Step 3: Implement one playback rate per narration unit**

```python
@dataclass(frozen=True, slots=True)
class AdaptiveEdlSegment:
    segment_id: str
    unit_id: str
    situation_id: str
    range_id: str
    source_start_ms: int
    source_end_ms: int
    program_start_ms: int
    program_end_ms: int
    playback_rate: float
    shot_ids: tuple[str, ...]
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdaptiveEdlDocument:
    segments: tuple[AdaptiveEdlSegment, ...]
    total_duration_ms: int


def choose_playback_rate(footage_ms: int, voice_ms: int, policy: EditorialPolicy) -> float:
    rate = footage_ms / voice_ms
    if not policy.minimum_playback_rate <= rate <= policy.maximum_playback_rate:
        raise MvpError("rewrite narration or select evidence; required playback rate is outside policy")
    return rate
```

For a unit with multiple evidence ranges, calculate the rate from their total source duration and the measured unit WAV duration. Convert every source segment to `round(source_duration / rate)` program milliseconds; assign any rounding remainder to the final segment so the unit end equals its WAV duration exactly. Call `validate_keep_skip()` before returning the document.

- [ ] **Step 4: Run adaptive and legacy EDL tests**

Run: `uv run pytest tests/unit/test_adaptive_edl.py tests/unit/test_edl.py tests/unit/test_atomic_edl_audit.py -v`

Expected: PASS; legacy EDL behavior remains unchanged for resumable old runs.

- [ ] **Step 5: Commit adaptive EDL**

```powershell
git add src/anime_review_mvp/adaptive_edl.py src/anime_review_mvp/situations.py tests/unit/test_adaptive_edl.py
git commit -m "feat: build adaptive keep-skip EDL"
```

### Task 6: Cache TTS by Situation and Render Variable-Speed Video

**Files:**
- Modify: `src/anime_review_mvp/tts.py`
- Modify: `src/anime_review_mvp/render.py`
- Create: `tests/unit/test_situation_tts.py`
- Modify: `tests/unit/test_render.py`
- Modify: `tests/integration/test_render_ffmpeg.py`

**Interfaces:**
- Consumes: locked `NarrationPlan`, Task 1's `SituationTts`/`SituationTtsManifest`, and `AdaptiveEdlDocument`.
- Produces: `synthesize_situation_units(...) -> SituationTtsManifest` and adaptive FFmpeg filter graph support.

- [ ] **Step 1: Write failing cache and FFmpeg graph tests**

```python
def test_tts_cache_only_regenerates_changed_unit(tmp_path: Path) -> None:
    first = synthesize_situation_units(PLAN, tmp_path / "out", tmp_path / "cache", provider=FAKE)
    second = synthesize_situation_units(CHANGED_SECOND_UNIT, tmp_path / "out2", tmp_path / "cache", provider=FAKE)
    assert second.cache_hits == 1
    assert second.cache_misses == 1


def test_filter_graph_applies_segment_playback_rate() -> None:
    graph = build_filter_graph(ADAPTIVE_EDL)
    assert "setpts=(PTS-STARTPTS)/1.250000" in graph
```

- [ ] **Step 2: Confirm tests fail before changing TTS/render**

Run: `uv run pytest tests/unit/test_situation_tts.py tests/unit/test_render.py -v`

Expected: FAIL because adaptive manifests and graph support do not exist.

- [ ] **Step 3: Implement situation-unit TTS cache**

Use a cache key over normalized narration text, voice ID, provider, policy version, and source SHA-256. Concatenate locked unit WAVs in story order. Do not reuse an entry when narration text changes, even if the unit ID is unchanged.

- [ ] **Step 4: Implement variable-speed video filters**

```python
filters.append(
    f"[0:v:0]trim=start={start:.3f}:end={end:.3f},"
    f"setpts=(PTS-STARTPTS)/{segment.playback_rate:.6f}[{label}]"
)
```

Keep source audio unmapped. Preserve proxy scaling and final encoding behavior. The rendered program duration must stay within `80 ms` of the concatenated narration WAV.

- [ ] **Step 5: Run TTS/render unit and FFmpeg integration tests**

Run: `uv run pytest tests/unit/test_situation_tts.py tests/unit/test_render.py tests/unit/test_tts.py tests/integration/test_render_ffmpeg.py -v`

Expected: PASS and the integration output has exactly one video stream plus one narration audio stream.

- [ ] **Step 6: Commit TTS and render support**

```powershell
git add src/anime_review_mvp/tts.py src/anime_review_mvp/render.py tests/unit/test_situation_tts.py tests/unit/test_render.py tests/integration/test_render_ffmpeg.py
git commit -m "feat: lock situation TTS to adaptive footage"
```

### Task 7: Add Local Semantic Audit and No-Progress Fingerprints

**Files:**
- Create: `src/anime_review_mvp/local_audit.py`
- Modify: `src/anime_review_mvp/workflow.py`
- Create: `tests/unit/test_local_audit.py`
- Modify: `tests/unit/test_workflow.py`

**Interfaces:**
- Consumes: narration plan, situation document, `SemanticReviewDocument`, source/program anchors, adaptive EDL, TTS manifest, render result, and repair finding codes.
- Produces: `load_semantic_review(path, plan, source_anchors, program_anchors) -> SemanticReviewDocument`, `build_local_audit(...) -> EngineAuditReport`, `content_fingerprint(paths) -> str`, `record_local_repair(run_dir, situation_ids, codes, fingerprint) -> RunState`, and per-situation lock progress.

- [ ] **Step 1: Write failing local-audit and repeated-fingerprint tests**

```python
def test_local_audit_rejects_claim_without_required_anchor() -> None:
    report = build_local_audit(PLAN, SITUATIONS, SOURCE_ANCHORS_MISSING_RESULT, PROGRAM_ANCHORS, EDL, TTS, RENDER)
    assert report.passed is False
    assert "UNSUPPORTED_STORY_CLAIM" in {item.code for item in report.findings}


def test_semantic_review_cannot_omit_or_invent_units(tmp_path: Path) -> None:
    with pytest.raises(MvpError, match="unit IDs must exactly match"):
        load_semantic_review(tmp_path / "semantic_review.json", PLAN, SOURCE_ANCHORS, PROGRAM_ANCHORS)


def test_second_identical_repair_stops_no_progress(tmp_path: Path) -> None:
    run = new_state(tmp_path / "run", stage=Stage.KIEM_DINH_LOCAL)
    first = record_local_repair(run.run_dir, ("situation-003",), ("VOICE_SCENE_MISMATCH",), "a" * 64)
    second = record_local_repair(run.run_dir, ("situation-003",), ("VOICE_SCENE_MISMATCH",), "a" * 64)
    assert second.stage is Stage.CAN_CON_NGUOI_XU_LY
    assert second.repair_history[-1].codes == ("KHONG_CO_TIEN_TRIEN",)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/unit/test_local_audit.py tests/unit/test_workflow.py -v`

Expected: FAIL because local audit stages and fingerprints are missing.

- [ ] **Step 3: Implement the default local state path**

```text
CHUAN_BI → QUAN_SAT → LAP_TINH_HUONG → VIET_LOI → TAO_TTS
→ CAN_HINH_VOICE → DUNG_PROXY → KIEM_DINH_LOCAL
→ DUNG_VIDEO_CUOI → KIEM_DINH_ENGINE → HOAN_THANH
```

Add `locked_situation_ids`, `current_situation_id`, and the latest local repair fingerprint/codes to `RunState`. `record_local_repair()` may be called again while the run is in its local repair stage so it can detect an unchanged attempted repair before any expensive TTS/render work. `read_state()` must accept old state files lacking these new fields and supply empty defaults; writing always emits the new schema. Only workflow functions may write state.

- [ ] **Step 4: Implement deterministic audit aggregation**

Require one semantic review entry for every narration unit and reject unknown/missing unit IDs or anchor IDs. Audit excluded ranges, forbidden start, claims/evidence, real gaps, clip length, rate bounds, TTS/EDL duration, A/V drift, source-audio absence, source/program frame anchors, and bridge continuity. A semantic agent may mark a claim unsupported, but it cannot mark technical checks passed.

- [ ] **Step 5: Run workflow and audit regressions**

Run: `uv run pytest tests/unit/test_local_audit.py tests/unit/test_workflow.py tests/unit/test_audit.py tests/unit/test_atomic_edl_audit.py -v`

Expected: PASS, including reading a legacy `run_state.json` fixture and stopping the second identical local repair.

- [ ] **Step 6: Commit audit and workflow**

```powershell
git add src/anime_review_mvp/local_audit.py src/anime_review_mvp/workflow.py tests/unit/test_local_audit.py tests/unit/test_workflow.py
git commit -m "feat: add local audit and no-progress stop"
```

### Task 8: Wire the Local-First CLI and Make Gemini Explicitly Optional

**Files:**
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `run_episode.py`
- Modify: `tests/unit/test_cli.py`
- Modify: `tests/unit/test_cli_antigravity.py`
- Create: `tests/unit/test_cli_situations.py`
- Modify: `docs/gemini-web-smoke.md`

**Interfaces:**
- Consumes: all interfaces from Tasks 1–7.
- Produces CLI commands `prepare`, `validate --artifact situations|narration|semantic-review|edl`, `tts --situation`, `render --quality proxy|final`, `audit --phase local|engine`, and retained `gemini-web ...` commands labeled optional.

- [ ] **Step 1: Write failing end-to-end CLI state tests**

```python
def test_default_cli_path_contains_no_gemini_stage(tmp_path: Path) -> None:
    run = prepared_run(tmp_path)
    execute_local_happy_path(run)
    states = read_recorded_stages(run)
    assert not any("GEMINI" in stage for stage in states)
    assert states[-1] == "HOAN_THANH"


def test_missing_ffmpeg_stops_before_transcription(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    result = main(["prepare", "--run", str(tmp_path / "run")])
    assert result == 2
    assert next_action(tmp_path / "run")["code"] == "THIEU_CONG_CU"
```

- [ ] **Step 2: Run CLI tests and verify the old Gemini-gated path fails expectations**

Run: `uv run pytest tests/unit/test_cli_situations.py tests/unit/test_cli.py tests/unit/test_cli_antigravity.py -v`

Expected: FAIL because the default path still advances through `CHO_GEMINI_*` stages.

- [ ] **Step 3: Move situation orchestration out of the monolithic CLI helpers**

Keep `cli.py` limited to argument parsing, artifact paths, calls into focused modules, stage transitions, and `next_action.json`. For each locked situation, `next_action.json` must name the exact next artifact/command. Do not allow direct `run_state.json` editing or automatic retries.

- [ ] **Step 4: Remove Gemini gates from the default commands**

After local script validation advance directly to TTS. After proxy local audit, advance to final render. Preserve `gemini-web` as an explicitly invoked diagnostic/audit command; it writes receipts under a separate optional-audit directory and never changes default run stage or calls `record_local_repair()`.

- [ ] **Step 5: Run CLI and full unit suites**

Run: `uv run pytest tests/unit -q`

Expected: PASS. Old Gemini-specific unit tests continue to pass for optional commands, while local-path tests prove Chrome is absent from the default workflow.

- [ ] **Step 6: Commit CLI integration**

```powershell
git add src/anime_review_mvp/cli.py run_episode.py tests/unit/test_cli.py tests/unit/test_cli_antigravity.py tests/unit/test_cli_situations.py docs/gemini-web-smoke.md
git commit -m "feat: make situation pipeline the default workflow"
```

### Task 9: Rebuild BLACK TORCH Episode 1 and Prove Generality

**Files:**
- Create: `tests/fixtures/situation_dialogue/`
- Create: `tests/fixtures/situation_action/`
- Create: `tests/integration/test_situation_pipeline.py`
- Runtime artifact only: `<episode>/Ke_hoach_canh/editorial_policy.json`
- Runtime outputs only: `<episode>/Kich_ban/situations.json`, `<episode>/Kich_ban/narration_plan.json`, `<episode>/TTS/`, `<episode>/Thanh_pham/`

**Interfaces:**
- Consumes the complete local-first CLI.
- Produces one tested dialogue fixture, one action fixture, and a rebuilt BLACK TORCH proxy/final without pre-river footage.

- [ ] **Step 1: Add compact dialogue-heavy and action-heavy fixtures**

The dialogue fixture must prove repeated dialogue/holds are shortened while revelations remain. The action fixture must prove ordinary exchanges are skipped while cause, power reveal, turning point, and outcome remain. Both fixtures must contain at least three kept ranges and three measurable omitted gaps.

- [ ] **Step 2: Write a failing integration test using the same policy engine**

```python
@pytest.mark.parametrize("fixture_name", ("situation_dialogue", "situation_action"))
def test_same_engine_handles_dialogue_and_action(fixture_name: str) -> None:
    result = run_fixture_pipeline(FIXTURES / fixture_name)
    assert result.audit.passed is True
    assert all(gap >= 500 for gap in result.omitted_gaps_ms)
    assert result.gemini_invocations == 0
```

- [ ] **Step 3: Run fixture integration tests**

Run: `uv run pytest tests/integration/test_situation_pipeline.py -v`

Expected: PASS for both fixtures with identical engine policy and no browser process.

- [ ] **Step 4: Create the BLACK TORCH run policy as episode data**

```json
{
  "minimum_clip_ms": 500,
  "minimum_omitted_gap_ms": 500,
  "minimum_playback_rate": 0.8,
  "maximum_playback_rate": 1.3,
  "forbidden_before_ms": 148482,
  "target_minimum_ms": 420000,
  "target_maximum_ms": 720000
}
```

Write this only under the episode/run artifact tree. Do not place `148482` in Python or shared policy defaults.

- [ ] **Step 5: Run preflight and stop if a required tool is missing**

Run: `uv run python run_episode.py prepare --run "D:\FINAL REVIEW ANIME\Tam_dang_xu_ly\db61e8cdf0764bbeaa067e75df5e5aeb"`

Expected: either successful local evidence preparation, or `THIEU_CONG_CU` naming the missing tool with no automatic installation.

- [ ] **Step 6: Regenerate situation/narration artifacts and render proxy locally**

Follow only the `next_action.json` commands emitted by the new local state path. Process and lock one situation at a time. Do not invoke `gemini-web`, do not edit `run_state.json`, and do not overwrite the final MP4 until the proxy passes local audit.

- [ ] **Step 7: Verify the proxy before final render**

Run: `uv run python run_episode.py audit --run "D:\FINAL REVIEW ANIME\Tam_dang_xu_ly\db61e8cdf0764bbeaa067e75df5e5aeb" --phase local`

Expected: PASS; first EDL source timestamp is `>= 148482`, every omitted gap is `>= 500 ms`, all speeds are within `0.80–1.30`, source/program anchors exist, no source audio is mapped, and no Gemini receipt is required.

- [ ] **Step 8: Render final, inspect start/middle/end, and run the entire test suite**

Run: `uv run pytest -q`

Expected: all tests PASS. Inspect the delivered MP4 frame at program `00:00`: it must show the riverside gang, not manga, childhood footage, logo, or title card. Verify one dialogue-heavy and one fight-heavy situation manually against narration and anchors.

- [ ] **Step 9: Commit only reusable fixtures/tests; keep episode media out of Git**

```powershell
git add tests/fixtures/situation_dialogue tests/fixtures/situation_action tests/integration/test_situation_pipeline.py
git commit -m "test: prove adaptive montage across anime situations"
```

Do not add generated WAV, MP4, source video, episode JSON, temporary frames, or user media to Git.

## Final Verification Checklist

- [ ] Run `uv run ruff check src tests` and expect no findings.
- [ ] Run `uv run pytest -q` and expect the full suite to pass.
- [ ] Confirm `git status --short` shows only pre-existing user changes and intended untracked media directories.
- [ ] Confirm the default stage history contains no `CHO_GEMINI_*` stage.
- [ ] Confirm a repeated unchanged repair stops on the second attempt with `KHONG_CO_TIEN_TRIEN`.
- [ ] Confirm BLACK TORCH starts at source `>= 148482 ms` and its first program frame is the riverside gang.
- [ ] Confirm every kept range has a real omitted interval after it, including the final source tail.
- [ ] Confirm the final contains exactly one video stream and one Vietnamese TTS audio stream.
- [ ] Confirm no dependency or plugin was installed automatically.
