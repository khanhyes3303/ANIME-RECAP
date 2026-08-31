# Antigravity Tagged Autonomous Episode Operator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a one-launch, resumable operator that lets tagged Antigravity analyze, edit, verify, and repair any anime episode through an evidence-complete proxy without requiring the user to relay individual situation prompts.

**Architecture:** Keep episode-specific judgment inside Antigravity jobs and keep deterministic state transitions, provenance, media extraction, and fail-closed validation in the local engine. Add independent situation and proxy verifier contracts, then make one `operator` command advance all engine-owned stages and prepare the next Antigravity-owned job. The persistent `goal` and `teamwork-preview` launch prompt instructs the Antigravity parent to continue the command/job loop until the user proxy gate.

**Tech Stack:** Python 3.12+, dataclasses, JSON/JSONL artifacts, pytest, FFmpeg/FFprobe, existing `anime_review_mvp` CLI and state machine.

**Spec:** `docs/superpowers/specs/2026-08-31-antigravity-tagged-autonomous-episode-operator-design.md`

## Global Constraints

- Antigravity is the only owner of video understanding, situation boundaries, narration, range selection, and semantic review.
- Codex and local code may generate packets, validate evidence, route repairs, normalize media, and advance state; they may not author editorial artifacts.
- The user attaches `teamwork-preview` and `goal` once and sends one generated launch prompt.
- Situation count is derived from the episode and must never be hard-coded.
- Every source interval and shot must be accounted for as editable or explicitly excluded.
- Every narration cue must be reviewed against source/program frames and transcript/SRT, or carry a valid visual-only justification.
- Gemini Web is not part of the default workflow.
- The system never installs missing dependencies; it stops with the exact missing tool or capability.
- The same finding set plus unchanged output fingerprint stops after two consecutive repair rounds.
- Proxy acceptance requires one video stream, one audio stream, at most 80 ms A/V drift, at most 100 ms voice lead, -14 LUFS target, true peak at most -1.5 dBTP, and complete Antigravity cue verdicts.
- Existing accepted revisions are immutable and unrelated dirty-worktree changes must be preserved.

## File Structure

- `src/anime_review_mvp/operator.py`: pure state-to-directive planning and operator stop reasons.
- `src/anime_review_mvp/review_contracts.py`: situation/proxy verifier schemas and loudness schema.
- `src/anime_review_mvp/review_packets.py`: scoped verifier packet builders and Antigravity prompts.
- `src/anime_review_mvp/editor_provenance.py`: producer/verifier task and acceptance provenance.
- `src/anime_review_mvp/workflow.py`: new verifier stages and resumable repair state.
- `src/anime_review_mvp/cli.py`: `operator`, `verifier-task`, and `accept-verifier` orchestration over existing commands.
- `src/anime_review_mvp/situation_index.py`: total source/shot coverage validation.
- `src/anime_review_mvp/situation_validation.py`: cue evidence and excluded-range validation.
- `src/anime_review_mvp/media.py`: per-cue source/program evidence and boundary frame extraction.
- `src/anime_review_mvp/render.py`: two-pass narration loudness normalization and measurement.
- `src/anime_review_mvp/local_audit.py`: objective plus Antigravity semantic proxy gates.
- `Bo_nao_Antigravity/GEMINI.md`, `Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md`, and `README.md`: one-launch tagged operating contract.

---

### Task 1: Make episode structure coverage exhaustive and dynamic

**Files:**
- Modify: `src/anime_review_mvp/situation_index.py`
- Modify: `src/anime_review_mvp/structure_packets.py`
- Test: `tests/unit/test_situation_index.py`
- Test: `tests/unit/test_structure_packets.py`

**Interfaces:**
- Consumes: `SituationIndexDocument`, `SourceRef`, `TranscriptDocument`, `ShotDocument`.
- Produces: `validate_situation_index(...) -> None` that rejects gaps, overlaps, off-boundary cuts, missing shots, duplicate shot ownership, and incomplete source coverage.

- [ ] **Step 1: Write failing coverage tests**

```python
def test_index_must_cover_source_without_gaps() -> None:
    index = document(
        entry("situation-001", 0, 5_000, shot_ids=("shot-001",)),
        entry("situation-002", 5_500, 10_000, shot_ids=("shot-002",)),
    )
    with pytest.raises(MvpError, match="SITUATION_INDEX_SOURCE_GAP"):
        validate_situation_index(index, source(10_000), transcript(), shots(), frames())


def test_every_shot_belongs_to_exactly_one_situation() -> None:
    index = document(
        entry("situation-001", 0, 5_000, shot_ids=("shot-001",)),
        entry("situation-002", 5_000, 10_000, shot_ids=("shot-001", "shot-002")),
    )
    with pytest.raises(MvpError, match="SITUATION_INDEX_SHOT_OWNERSHIP_INVALID"):
        validate_situation_index(index, source(10_000), transcript(), shots(), frames())
```

- [ ] **Step 2: Run the new tests and confirm the current validator accepts the invalid cases**

Run: `uv run pytest -q tests/unit/test_situation_index.py`

Expected: the new tests fail because the current validator only rejects overlap/order errors and does not require continuous source or exact shot ownership.

- [ ] **Step 3: Implement exact source and shot coverage**

Add these checks after existing reference validation:

```python
if index.situations[0].source_start_ms != 0:
    raise MvpError("SITUATION_INDEX_SOURCE_GAP: first situation must begin at 0")
for previous, current in zip(index.situations, index.situations[1:], strict=False):
    if previous.source_end_ms != current.source_start_ms:
        raise MvpError("SITUATION_INDEX_SOURCE_GAP: situation ranges must be contiguous")
if index.situations[-1].source_end_ms != source.duration_ms:
    raise MvpError("SITUATION_INDEX_SOURCE_GAP: final situation must end at source duration")

observed_shots = [shot_id for item in index.situations for shot_id in item.shot_ids]
expected_shots = [shot.shot_id for shot in shots.shots]
if sorted(observed_shots) != sorted(expected_shots) or len(observed_shots) != len(set(observed_shots)):
    raise MvpError("SITUATION_INDEX_SHOT_OWNERSHIP_INVALID")
```

Also update the structure prompt to say the first range starts at 0, the last ends at the measured source duration, adjacent ranges share a boundary, and every shot ID appears exactly once.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest -q tests/unit/test_situation_index.py tests/unit/test_structure_packets.py`

Expected: all focused tests pass.

- [ ] **Step 5: Commit the coverage gate**

```powershell
git add src/anime_review_mvp/situation_index.py src/anime_review_mvp/structure_packets.py tests/unit/test_situation_index.py tests/unit/test_structure_packets.py
git commit -m "feat: require exhaustive episode situation coverage"
```

### Task 2: Add independent verifier schemas and provenance

**Files:**
- Create: `src/anime_review_mvp/review_contracts.py`
- Modify: `src/anime_review_mvp/editor_provenance.py`
- Create: `tests/unit/test_review_contracts.py`
- Modify: `tests/unit/test_editor_provenance.py`

**Interfaces:**
- Consumes: producer task IDs, cue IDs, situation IDs, transcript refs, frame refs, and finding codes.
- Produces: `CueSemanticVerdict`, `BoundaryVerdict`, `SituationAuditDocument`, `ProxyAuditDocument`, `LoudnessReport`, and verifier acceptance records.

- [ ] **Step 1: Write failing schema tests**

```python
def test_situation_audit_requires_one_evidence_backed_verdict_per_cue() -> None:
    with pytest.raises(MvpError, match="VERIFIER_EVIDENCE_REQUIRED"):
        CueSemanticVerdict(
            cue_id="cue-001",
            situation_id="situation-001",
            verdict="MATCH",
            observed_visual="Jiro gặp Rago.",
            narration_meaning="Jiro tìm thấy Rago.",
            transcript_refs=(),
            frame_refs=(),
            visual_only=False,
            voice_before_visual=False,
            mixed_semantics=False,
            finding_codes=(),
            note="Khớp.",
        )


def test_producer_and_verifier_contexts_must_differ() -> None:
    with pytest.raises(MvpError, match="VERIFIER_CONTEXT_NOT_INDEPENDENT"):
        SituationAuditDocument(
            editor="ANTIGRAVITY_VERIFIER",
            policy_version="situation-v3",
            producer_task_id="situation-001-revision-001",
            producer_context_id="context-a",
            verifier_context_id="context-a",
            cue_reviews=(valid_cue_review(),),
        )
```

- [ ] **Step 2: Run the tests and verify import/schema failures**

Run: `uv run pytest -q tests/unit/test_review_contracts.py tests/unit/test_editor_provenance.py`

Expected: FAIL because the verifier models and task kinds do not exist.

- [ ] **Step 3: Implement the contracts**

Create frozen dataclasses with these public shapes:

```python
@dataclass(frozen=True, slots=True)
class CueSemanticVerdict:
    cue_id: str
    situation_id: str
    verdict: str  # MATCH | MISMATCH | INSUFFICIENT_EVIDENCE
    observed_visual: str
    narration_meaning: str
    transcript_refs: tuple[str, ...]
    frame_refs: tuple[str, ...]
    visual_only: bool
    voice_before_visual: bool
    mixed_semantics: bool
    finding_codes: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class BoundaryVerdict:
    boundary: str  # START | END
    verdict: str  # CLEAN | LEAKED_EXCLUDED_CONTENT | INSUFFICIENT_EVIDENCE
    frame_refs: tuple[str, ...]
    transcript_refs: tuple[str, ...]
    finding_codes: tuple[str, ...]
    note: str


@dataclass(frozen=True, slots=True)
class LoudnessReport:
    integrated_lufs: float
    true_peak_dbtp: float
    loudness_range_lu: float
    normalized_audio_path: str


@dataclass(frozen=True, slots=True)
class SituationAuditDocument:
    editor: str
    policy_version: str
    producer_task_id: str
    producer_context_id: str
    verifier_context_id: str
    cue_reviews: tuple[CueSemanticVerdict, ...]


@dataclass(frozen=True, slots=True)
class ProxyAuditDocument:
    editor: str
    policy_version: str
    producer_context_id: str
    verifier_context_id: str
    cue_reviews: tuple[CueSemanticVerdict, ...]
    boundary_reviews: tuple[BoundaryVerdict, ...]
```

Extend `EditorTask.task_kind` to accept `STRUCTURE`, `SITUATION`, `SITUATION_AUDIT`, and `PROXY_AUDIT`. Add a generic `AcceptedVerifierRevision` with `task_id`, `run_id`, `task_kind`, `situation_id`, `revision`, `actor`, `input_sha256`, and `audit_sha256`, stored in `verifier_ledger.jsonl`.

- [ ] **Step 4: Run focused tests**

Run: `uv run pytest -q tests/unit/test_review_contracts.py tests/unit/test_editor_provenance.py`

Expected: all focused tests pass.

- [ ] **Step 5: Commit verifier contracts**

```powershell
git add src/anime_review_mvp/review_contracts.py src/anime_review_mvp/editor_provenance.py tests/unit/test_review_contracts.py tests/unit/test_editor_provenance.py
git commit -m "feat: add independent Antigravity verifier contracts"
```

### Task 3: Extend the workflow for verifier stages and no-progress stops

**Files:**
- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `tests/unit/test_workflow.py`

**Interfaces:**
- Consumes: accepted producer revisions and verifier findings.
- Produces: explicit verifier wait/validation stages and `route_verifier_repair(...) -> RunState`.

- [ ] **Step 1: Write failing transition and repair-loop tests**

```python
def test_situation_must_pass_independent_verifier_before_locking(tmp_path: Path) -> None:
    run = tmp_path / "run"
    new_state(run, stage=Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG)
    waiting = advance(
        run,
        Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG,
        Stage.CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG,
    )
    assert waiting.stage is Stage.CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG


def test_same_verifier_failure_twice_stops_for_human(tmp_path: Path) -> None:
    run = seeded_verifier_run(tmp_path)
    route_verifier_repair(run, "situation-004", ("SCENE_MISMATCH",), "a" * 64)
    stopped = route_verifier_repair(run, "situation-004", ("SCENE_MISMATCH",), "a" * 64)
    assert stopped.stage is Stage.CAN_CON_NGUOI_XU_LY
```

- [ ] **Step 2: Run workflow tests and verify missing-stage failures**

Run: `uv run pytest -q tests/unit/test_workflow.py`

Expected: FAIL because verifier stages and routing do not exist.

- [ ] **Step 3: Implement the state transitions**

Add stages:

```python
CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG = "CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG"
KIEM_DINH_PHAN_BIEN_TINH_HUONG = "KIEM_DINH_PHAN_BIEN_TINH_HUONG"
CHO_ANTIGRAVITY_KIEM_DINH_PROXY = "CHO_ANTIGRAVITY_KIEM_DINH_PROXY"
KIEM_DINH_PHAN_BIEN_PROXY = "KIEM_DINH_PHAN_BIEN_PROXY"
```

Add corresponding v2 transitions. Extend `RunState` with `verifier_task_id`, `last_verifier_fingerprint`, `last_verifier_codes`, and `verifier_stall_count`. Implement `route_verifier_repair()` so a changed fingerprint resets the count, one unchanged repeat increments it, and the second unchanged occurrence calls `mark_human_required(..., "ANTIGRAVITY_VERIFIER_NO_PROGRESS")`.

- [ ] **Step 4: Run workflow tests**

Run: `uv run pytest -q tests/unit/test_workflow.py`

Expected: all workflow tests pass.

- [ ] **Step 5: Commit state-machine changes**

```powershell
git add src/anime_review_mvp/workflow.py tests/unit/test_workflow.py
git commit -m "feat: add Antigravity verifier workflow stages"
```

### Task 4: Build tagged launch and a pure operator planner

**Files:**
- Create: `src/anime_review_mvp/operator.py`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/antigravity.py`
- Create: `tests/unit/test_operator.py`
- Modify: `tests/unit/test_cli.py`
- Modify: `tests/unit/test_antigravity_contract.py`

**Interfaces:**
- Consumes: `RunState` and presence of required run artifacts.
- Produces: `OperatorDirective`, `plan_operator_step(...)`, CLI `operator --run`, and one tagged launch prompt.

- [ ] **Step 1: Write failing planner tests for arbitrary situation counts and terminal gates**

```python
def test_operator_requests_next_unlocked_situation_without_a_fixed_count() -> None:
    directive = plan_operator_step(
        state(stage=Stage.CHO_ANTIGRAVITY_TINH_HUONG, locked=("situation-001",)),
        editable_ids=("situation-001", "situation-002", "situation-003"),
    )
    assert directive.action == "PREPARE_SITUATION_JOB"
    assert directive.situation_id == "situation-002"


def test_operator_stops_only_at_user_proxy_gate() -> None:
    directive = plan_operator_step(
        state(stage=Stage.CHO_NGUOI_DUNG_DUYET_PROXY), editable_ids=()
    )
    assert directive.action == "WAIT_FOR_USER_PROXY_APPROVAL"
```

- [ ] **Step 2: Run planner tests and confirm missing module/parser failures**

Run: `uv run pytest -q tests/unit/test_operator.py tests/unit/test_cli.py tests/unit/test_antigravity_contract.py`

Expected: FAIL because `operator.py`, the directive API, and CLI command are absent.

- [ ] **Step 3: Implement the pure planner and CLI dispatch**

```python
@dataclass(frozen=True, slots=True)
class OperatorDirective:
    action: str
    situation_id: str = ""
    stop_code: str = ""


def plan_operator_step(
    state: RunState, *, editable_ids: tuple[str, ...]
) -> OperatorDirective:
    if state.stage is Stage.CHO_NGUOI_DUNG_DUYET_PROXY:
        return OperatorDirective("WAIT_FOR_USER_PROXY_APPROVAL")
    if state.stage is Stage.CAN_CON_NGUOI_XU_LY:
        return OperatorDirective("STOP", stop_code="HUMAN_REQUIRED")
    if state.stage is Stage.CHO_ANTIGRAVITY_TINH_HUONG:
        next_id = next(
            (item for item in editable_ids if item not in state.locked_situation_ids),
            "",
        )
        if next_id:
            return OperatorDirective("PREPARE_SITUATION_JOB", next_id)
        return OperatorDirective("RUN_ENGINE_STAGE")
    return OperatorDirective("RUN_ENGINE_STAGE")
```

Add parser command `operator --run <path>`. `_operator_command()` repeatedly executes deterministic local stages until it has prepared an Antigravity job, reaches the user gate, or reaches a human stop. It prints a machine-readable `operator_status.json` containing `action`, `stage`, `task_id`, and `instruction`.

- [ ] **Step 4: Generate the one-launch prompt contract**

Update `_prompt()`/`antigravity.py` so `PROMPT_GUI_ANTIGRAVITY.txt` explicitly requires the user-attached `goal` and `teamwork-preview` capabilities and tells the Antigravity parent:

```text
Mục tiêu duy nhất: đưa run đến CHO_NGUOI_DUNG_DUYET_PROXY.
Không kết thúc goal sau STRUCTURE hoặc một SITUATION.
Sau mỗi lần accept thành công, chạy lại:
uv run python run_episode.py operator --run "<run_dir>"
Nếu thiếu goal hoặc teamwork-preview, báo ANTIGRAVITY_CAPABILITY_MISSING và dừng.
```

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest -q tests/unit/test_operator.py tests/unit/test_cli.py tests/unit/test_antigravity_contract.py`

Expected: all focused tests pass and the generated prompt contains both tag names exactly once.

- [ ] **Step 6: Commit the operator skeleton**

```powershell
git add src/anime_review_mvp/operator.py src/anime_review_mvp/cli.py src/anime_review_mvp/antigravity.py tests/unit/test_operator.py tests/unit/test_cli.py tests/unit/test_antigravity_contract.py
git commit -m "feat: add tagged autonomous episode operator"
```

### Task 5: Add situation verifier packets, acceptance, and repair routing

**Files:**
- Create: `src/anime_review_mvp/review_packets.py`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/local_audit.py`
- Create: `tests/unit/test_review_packets.py`
- Modify: `tests/unit/test_cli_situations.py`
- Modify: `tests/unit/test_local_audit.py`

**Interfaces:**
- Consumes: accepted situation/narration drafts, scoped frames/shots/transcript, producer context ID.
- Produces: `build_situation_audit_packet(...)`, `render_situation_audit_prompt(...)`, CLI `verifier-task --kind situation`, and `accept-verifier` validation.

- [ ] **Step 1: Write failing packet and per-cue verdict tests**

```python
def test_situation_verifier_packet_contains_only_one_situation() -> None:
    packet = build_situation_audit_packet(scope, plan, producer_task, verifier_task)
    assert packet.situation_id == "situation-004"
    assert {cue.situation_id for cue in packet.cues} == {"situation-004"}
    assert packet.required_outputs == ("situation_audit_draft.json",)


def test_situation_audit_rejects_missing_cue_verdict() -> None:
    with pytest.raises(MvpError, match="SITUATION_AUDIT_CUE_COVERAGE_INVALID"):
        validate_situation_audit(audit_for("cue-001"), plan_with("cue-001", "cue-002"))
```

- [ ] **Step 2: Run focused tests and confirm missing API failures**

Run: `uv run pytest -q tests/unit/test_review_packets.py tests/unit/test_cli_situations.py tests/unit/test_local_audit.py`

Expected: FAIL because verifier packets and validation are absent.

- [ ] **Step 3: Implement scoped verifier packets and prompts**

Define `SituationAuditPacket` with exact source path, scoped transcript/shots/frames, accepted drafts, producer/verifier context IDs, and one required output. The rendered prompt must require the verifier to inspect every cue, forbid modification of producer artifacts, and require `MISMATCH` or `INSUFFICIENT_EVIDENCE` whenever the referenced frames/transcript do not prove the narration.

Derive `producer_context_id` from the immutable accepted producer record (for example `producer:<task_id>:<input_sha256>`) and record the `verifier_context_id` supplied by the independent `teamwork-preview` verifier. Neither value is user-authored, and equality is rejected by the contract from Task 2.

- [ ] **Step 4: Wire acceptance into the workflow**

After local semantic timing succeeds, advance to `CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG` instead of locking. `verifier-task --kind situation` prepares the audit job. `accept-verifier` validates exact cue ID coverage, real evidence refs, distinct producer/verifier contexts, and MATCH-only success. Findings call `route_editor_repair()` for the current situation; complete success calls `lock_editor_situation()` and lets `operator` continue.

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest -q tests/unit/test_review_packets.py tests/unit/test_cli_situations.py tests/unit/test_local_audit.py`

Expected: all focused tests pass.

- [ ] **Step 6: Commit situation verification**

```powershell
git add src/anime_review_mvp/review_packets.py src/anime_review_mvp/cli.py src/anime_review_mvp/local_audit.py tests/unit/test_review_packets.py tests/unit/test_cli_situations.py tests/unit/test_local_audit.py
git commit -m "feat: require Antigravity verification for every situation cue"
```

### Task 6: Block excluded footage and extract complete cue/boundary evidence

**Files:**
- Modify: `src/anime_review_mvp/models.py`
- Modify: `src/anime_review_mvp/media.py`
- Modify: `src/anime_review_mvp/situation_validation.py`
- Create: `src/anime_review_mvp/proxy_evidence.py`
- Modify: `tests/unit/test_media.py`
- Modify: `tests/unit/test_situation_validation.py`
- Create: `tests/unit/test_proxy_evidence.py`

**Interfaces:**
- Consumes: `NarrationPlan`, `SemanticTimeline`, `AdaptiveEdlDocument`, `SituationIndexDocument`, source video, proxy video, and transcript.
- Produces: `extract_cue_proxy_evidence(...) -> ProxyEvidenceManifest` and `validate_edl_exclusions(...) -> None`.

- [ ] **Step 1: Write failing excluded-frame and anchor coverage tests**

```python
def test_edl_cannot_overlap_an_excluded_interval_by_one_millisecond() -> None:
    with pytest.raises(MvpError, match="EDL_EXCLUDED_SOURCE_OVERLAP"):
        validate_edl_exclusions(
            edl_segment(9_999, 12_000),
            index_with_excluded_range(0, 10_000),
        )


def test_proxy_evidence_has_start_anchor_middle_end_for_every_cue(tmp_path: Path) -> None:
    manifest = extract_cue_proxy_evidence(
        source, proxy, plan, timeline, edl, transcript, tmp_path, runner=fake_runner
    )
    assert tuple(frame.position for frame in manifest.cues[0].program_frames) == (
        "START", "ANCHOR", "MIDDLE", "END"
    )
```

- [ ] **Step 2: Run the tests and verify missing validation/extractor failures**

Run: `uv run pytest -q tests/unit/test_media.py tests/unit/test_situation_validation.py tests/unit/test_proxy_evidence.py`

Expected: FAIL because ANCHOR frames, excluded-overlap validation, and cue manifests are absent.

- [ ] **Step 3: Implement exact exclusion validation**

```python
def validate_edl_exclusions(
    edl: AdaptiveEdlDocument,
    index: SituationIndexDocument,
) -> None:
    excluded = tuple(item for item in index.situations if item.excluded)
    for segment in edl.segments:
        for item in excluded:
            if max(segment.source_start_ms, item.source_start_ms) < min(
                segment.source_end_ms, item.source_end_ms
            ):
                raise MvpError("EDL_EXCLUDED_SOURCE_OVERLAP")
```

Call it during timeline/EDL validation before render.

- [ ] **Step 4: Implement cue and boundary evidence extraction**

Allow `FrameAnchor.position == "ANCHOR"`. Define these frozen public data shapes in `proxy_evidence.py`:

```python
@dataclass(frozen=True, slots=True)
class ProxyEvidenceFrame:
    position: str  # START | ANCHOR | MIDDLE | END
    timestamp_ms: int
    path: str


@dataclass(frozen=True, slots=True)
class CueProxyEvidence:
    cue_id: str
    situation_id: str
    source_interval_ms: tuple[int, int]
    program_interval_ms: tuple[int, int]
    source_frames: tuple[ProxyEvidenceFrame, ...]
    program_frames: tuple[ProxyEvidenceFrame, ...]
    transcript_segment_indexes: tuple[int, ...]
    transcript_text: tuple[str, ...]
    shot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BoundaryProxyEvidence:
    boundary: str  # START | END
    program_frames: tuple[ProxyEvidenceFrame, ...]
    adjacent_excluded_source_intervals_ms: tuple[tuple[int, int], ...]
    transcript_segment_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ProxyEvidenceManifest:
    cues: tuple[CueProxyEvidence, ...]
    boundaries: tuple[BoundaryProxyEvidence, ...]
```

Build one `CueProxyEvidence` per cue containing source/program START, ANCHOR, MIDDLE, END images, overlapping transcript segment indexes/text, source/program intervals, and all referenced shots. Add separate START and END `BoundaryProxyEvidence` entries using the first/last kept program sequences and neighboring excluded source intervals.

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest -q tests/unit/test_media.py tests/unit/test_situation_validation.py tests/unit/test_proxy_evidence.py`

Expected: all focused tests pass.

- [ ] **Step 6: Commit evidence gates**

```powershell
git add src/anime_review_mvp/models.py src/anime_review_mvp/media.py src/anime_review_mvp/situation_validation.py src/anime_review_mvp/proxy_evidence.py tests/unit/test_media.py tests/unit/test_situation_validation.py tests/unit/test_proxy_evidence.py
git commit -m "feat: enforce excluded footage and cue evidence coverage"
```

### Task 7: Normalize and verify narration loudness

**Files:**
- Modify: `src/anime_review_mvp/render.py`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/local_audit.py`
- Modify: `tests/unit/test_render.py`
- Modify: `tests/integration/test_render_ffmpeg.py`
- Modify: `tests/unit/test_local_audit.py`

**Interfaces:**
- Consumes: aligned narration WAV and FFmpeg/FFprobe.
- Produces: `normalize_narration_loudness(...) -> LoudnessReport` and loudness-gated proxy/final renders.

- [ ] **Step 1: Write failing two-pass normalization and audit tests**

```python
def test_loudness_normalization_uses_measured_two_pass_filter(tmp_path: Path) -> None:
    report = normalize_narration_loudness(
        tmp_path / "aligned.wav",
        tmp_path / "normalized.wav",
        runner=loudness_runner(),
    )
    assert report.integrated_lufs == pytest.approx(-14.0, abs=1.0)
    assert report.true_peak_dbtp <= -1.5
    assert report.normalized_audio_path.endswith("normalized.wav")


def test_proxy_audit_rejects_quiet_narration() -> None:
    report = build_v2_local_audit(..., loudness=LoudnessReport(-24.0, -3.0, 4.0, "n.wav"))
    assert "NARRATION_LOUDNESS_OUT_OF_RANGE" in finding_codes(report)
```

- [ ] **Step 2: Run focused tests and confirm missing loudness API failures**

Run: `uv run pytest -q tests/unit/test_render.py tests/unit/test_local_audit.py`

Expected: FAIL because loudness normalization/reporting is absent.

- [ ] **Step 3: Implement FFmpeg loudnorm measurement and normalization**

The first pass runs:

```text
ffmpeg -v error -i aligned.wav -af loudnorm=I=-14:LRA=7:TP=-1.5:print_format=json -f null NUL
```

Parse `input_i`, `input_tp`, `input_lra`, `input_thresh`, and `target_offset`. The second pass applies:

```text
loudnorm=I=-14:LRA=7:TP=-1.5:measured_I=<input_i>:measured_TP=<input_tp>:measured_LRA=<input_lra>:measured_thresh=<input_thresh>:offset=<target_offset>:linear=true:print_format=json
```

Write `normalized_narration.wav`, measure it again, and persist `loudness_report.json`. Reject integrated loudness outside -15 to -13 LUFS, true peak above -1.5 dBTP, or loudness range above 7 LU.

- [ ] **Step 4: Render with normalized narration**

In the adaptive proxy/final branches, call normalization after aligned narration exists and pass `normalized_narration.wav` to `render_review()`. Add the report to `build_v2_local_audit()` and its objective findings.

- [ ] **Step 5: Run unit and real FFmpeg tests**

Run: `uv run pytest -q tests/unit/test_render.py tests/unit/test_local_audit.py tests/integration/test_render_ffmpeg.py`

Expected: all focused tests pass; the integration render measures within the configured loudness tolerance.

- [ ] **Step 6: Commit loudness normalization**

```powershell
git add src/anime_review_mvp/render.py src/anime_review_mvp/cli.py src/anime_review_mvp/local_audit.py tests/unit/test_render.py tests/integration/test_render_ffmpeg.py tests/unit/test_local_audit.py
git commit -m "feat: normalize and gate narration loudness"
```

### Task 8: Add full Antigravity proxy audit and precise repair routing

**Files:**
- Modify: `src/anime_review_mvp/review_packets.py`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/local_audit.py`
- Modify: `src/anime_review_mvp/proxy_approval.py`
- Modify: `tests/unit/test_review_packets.py`
- Modify: `tests/unit/test_cli_situations.py`
- Modify: `tests/unit/test_local_audit.py`
- Modify: `tests/unit/test_proxy_approval.py`

**Interfaces:**
- Consumes: proxy evidence manifest, loudness report, plan, timeline, EDL, render result, and independent `ProxyAuditDocument`.
- Produces: `build_proxy_audit_packet(...)`, `validate_proxy_audit(...)`, exact situation/cue repair routing, and a protected user approval gate.

- [ ] **Step 1: Write failing complete-proxy-audit tests**

```python
def test_proxy_audit_requires_exactly_one_match_for_every_cue() -> None:
    with pytest.raises(MvpError, match="PROXY_AUDIT_CUE_COVERAGE_INVALID"):
        validate_proxy_audit(
            proxy_audit(cue_reviews=(match("cue-001"),)),
            plan_with("cue-001", "cue-002"),
            evidence_for("cue-001", "cue-002"),
        )


def test_proxy_cannot_reach_user_gate_when_start_boundary_contains_intro() -> None:
    result = validate_proxy_audit(
        proxy_audit(boundary_reviews=(leaked_start_boundary(), clean_end_boundary())),
        plan,
        evidence,
    )
    assert "INTRO_OPENING_LEAK" in result.finding_codes
```

- [ ] **Step 2: Run focused tests and verify current local-only proxy audit fails the requirements**

Run: `uv run pytest -q tests/unit/test_review_packets.py tests/unit/test_cli_situations.py tests/unit/test_local_audit.py tests/unit/test_proxy_approval.py`

Expected: FAIL because current `_audit_proxy_v2()` reaches user approval without an Antigravity proxy audit.

- [ ] **Step 3: Implement proxy verifier packet and prompt**

The packet contains one entry per cue with all source/program evidence plus START/END boundary packets and `loudness_report.json`. The prompt requires an independent verifier context and forbids a blanket PASS. `required_outputs` is exactly `("proxy_audit_draft.json",)`.

- [ ] **Step 4: Implement acceptance and routing**

Change the proxy flow to:

```text
DUNG_PROXY
-> KIEM_DINH_PROXY (objective engine checks)
-> CHO_ANTIGRAVITY_KIEM_DINH_PROXY (prepare verifier job)
-> KIEM_DINH_PHAN_BIEN_PROXY (accept and validate verifier output)
-> CHO_NGUOI_DUNG_DUYET_PROXY
```

For `MISMATCH` or `INSUFFICIENT_EVIDENCE`, collect exact `situation_id` and `cue_id`, route only those situations through `route_verifier_repair()`, invalidate downstream TTS/timeline/proxy fingerprints, and let `operator` resume. `approve_proxy()` must require the accepted proxy verifier ledger hash in addition to existing artifacts.

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest -q tests/unit/test_review_packets.py tests/unit/test_cli_situations.py tests/unit/test_local_audit.py tests/unit/test_proxy_approval.py`

Expected: all focused tests pass.

- [ ] **Step 6: Commit proxy verification**

```powershell
git add src/anime_review_mvp/review_packets.py src/anime_review_mvp/cli.py src/anime_review_mvp/local_audit.py src/anime_review_mvp/proxy_approval.py tests/unit/test_review_packets.py tests/unit/test_cli_situations.py tests/unit/test_local_audit.py tests/unit/test_proxy_approval.py
git commit -m "feat: require evidence-complete Antigravity proxy audit"
```

### Task 9: Make the operator autonomous, resumable, and safe

**Files:**
- Modify: `src/anime_review_mvp/operator.py`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `tests/unit/test_operator.py`
- Create: `tests/integration/test_autonomous_operator.py`

**Interfaces:**
- Consumes: the completed state machine and all producer/verifier commands.
- Produces: repeated deterministic advancement, resumability, exact stop codes, and no manual situation relay.

- [ ] **Step 1: Write a failing arbitrary-count integration test**

Define `seeded_episode_run(...)`, `interrupted_after_two_situations(...)`, `FakeAntigravityAdapter`, and the test-only `drive_operator_until_stop(...)` harness at the top of `tests/integration/test_autonomous_operator.py`. The fake adapter implements `complete_prepared_job(run_dir: Path, directive: OperatorDirective) -> None`, records producer/verifier calls, and writes contract-valid fixtures before invoking the real acceptance commands. The harness repeatedly invokes the real `_operator_command()` and lets the adapter complete each prepared Antigravity job; it is not a production API and never substitutes for Antigravity outside this integration test.

```python
@pytest.mark.parametrize("count", (1, 3, 47))
def test_one_launch_processes_every_dynamic_situation_without_user_relay(
    tmp_path: Path, count: int
) -> None:
    run = seeded_episode_run(tmp_path, situation_count=count)
    adapter = FakeAntigravityAdapter.always_match()
    result = drive_operator_until_stop(run, adapter)
    assert result.stage is Stage.CHO_NGUOI_DUNG_DUYET_PROXY
    assert read_state(run).locked_situation_ids == tuple(
        f"situation-{index:03d}" for index in range(1, count + 1)
    )
    assert adapter.user_relay_count == 0
```

- [ ] **Step 2: Write failing interruption and no-progress tests**

```python
def test_operator_resumes_after_interruption_without_reediting_locked_work(tmp_path: Path) -> None:
    run, adapter = interrupted_after_two_situations(tmp_path)
    resumed = drive_operator_until_stop(run, adapter)
    assert resumed.stage is Stage.CHO_NGUOI_DUNG_DUYET_PROXY
    assert adapter.producer_calls["situation-001"] == 1
    assert adapter.producer_calls["situation-002"] == 1


def test_operator_stops_after_two_identical_failed_revisions(tmp_path: Path) -> None:
    run = seeded_episode_run(tmp_path, situation_count=1)
    result = drive_operator_until_stop(run, FakeAntigravityAdapter.repeating_mismatch())
    assert result.stage is Stage.CAN_CON_NGUOI_XU_LY
    assert next_action(run)["code"] == "ANTIGRAVITY_VERIFIER_NO_PROGRESS"
```

- [ ] **Step 3: Run integration tests and verify autonomous-loop failures**

Run: `uv run pytest -q tests/unit/test_operator.py tests/integration/test_autonomous_operator.py`

Expected: FAIL because the operator does not yet drive the full producer/verifier cycle.

- [ ] **Step 4: Implement production CLI loop behavior**

The production operator repeatedly calls the pure planner and engine-owned actions. It never fabricates Antigravity outputs and has no `FakeAntigravityAdapter` dependency. At an Antigravity action it prepares the exact job and exits successfully with `action="ANTIGRAVITY_WORK_REQUIRED"`; the tagged Antigravity parent completes that job, runs its acceptance command, and invokes `operator` again. Locked fingerprints skip completed work. Any missing executable is written to `next_action.json` as `MISSING_REQUIRED_TOOL:<name>`.

- [ ] **Step 5: Run unit and integration tests**

Run: `uv run pytest -q tests/unit/test_operator.py tests/integration/test_autonomous_operator.py`

Expected: all tests pass for 1, 3, and 47 situations, interruption resume, changed-fingerprint repair, and repeated-fingerprint stop.

- [ ] **Step 6: Commit the completed loop**

```powershell
git add src/anime_review_mvp/operator.py src/anime_review_mvp/cli.py src/anime_review_mvp/workflow.py tests/unit/test_operator.py tests/integration/test_autonomous_operator.py
git commit -m "feat: complete resumable autonomous Antigravity loop"
```

### Task 10: Update Antigravity policy, user documentation, and migration

**Files:**
- Modify: `Bo_nao_Antigravity/GEMINI.md`
- Modify: `Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md`
- Modify: `README.md`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `tests/unit/test_antigravity_contract.py`
- Modify: `tests/unit/test_cli_situations.py`

**Interfaces:**
- Consumes: all implemented commands and task contracts.
- Produces: one user-facing launch procedure and a migration path for existing runs.

- [ ] **Step 1: Write failing contract tests for the final instructions**

```python
def test_policy_requires_tagged_goal_to_continue_until_proxy_gate() -> None:
    policy = Path("Bo_nao_Antigravity/GEMINI.md").read_text(encoding="utf-8")
    assert "teamwork-preview" in policy
    assert "goal" in policy
    assert "CHO_NGUOI_DUNG_DUYET_PROXY" in policy
    assert "không kết thúc sau một situation" in policy.casefold()


def test_next_action_never_asks_user_to_copy_the_next_situation(tmp_path: Path) -> None:
    run = completed_situation_run(tmp_path)
    cli._operator_command(run)
    instruction = next_action(run)["instruction"].casefold()
    assert "copy" not in instruction
    assert "gửi" not in instruction
```

- [ ] **Step 2: Run contract tests and verify current documentation fails**

Run: `uv run pytest -q tests/unit/test_antigravity_contract.py tests/unit/test_cli_situations.py`

Expected: FAIL because current policy says one current situation per turn and the README still describes manual handoff.

- [ ] **Step 3: Update policy and README**

Document the exact launch sequence:

```powershell
uv run python run_episode.py start --anime "Ten Anime" --season 1 --episode 1 --video "D:\Tap01.mp4"
uv run python run_episode.py prepare --run "<run_dir>"
uv run python run_episode.py prompt --run "<run_dir>"
```

Then instruct the user to attach `teamwork-preview` and `goal` and send the generated prompt once. Clarify that the Antigravity parent keeps control while subagents divide evidence/editor/verifier roles, and only the proxy approval returns to the user.

- [ ] **Step 4: Add safe existing-run migration**

Extend `migrate-run` with reason `autonomous-operator`. It preserves accepted structure/editor/verifier ledgers, rebuilds only missing operator metadata, and chooses the next state from existing locked situations and proxy artifacts. It never deletes accepted revisions.

- [ ] **Step 5: Run documentation and migration tests**

Run: `uv run pytest -q tests/unit/test_antigravity_contract.py tests/unit/test_cli_situations.py`

Expected: all focused tests pass.

- [ ] **Step 6: Commit docs and migration**

```powershell
git add Bo_nao_Antigravity/GEMINI.md Bo_nao_Antigravity/PROMPT_MOT_LAN_CHAY.md README.md src/anime_review_mvp/cli.py tests/unit/test_antigravity_contract.py tests/unit/test_cli_situations.py
git commit -m "docs: make tagged Antigravity launch the only workflow"
```

### Task 11: Full verification and real-run checkpoint

**Files:**
- Modify only if verification exposes a tested defect in files already named above.
- Test: all tests under `tests/`.

**Interfaces:**
- Consumes: the complete implementation.
- Produces: clean automated verification evidence and one real run stopped at the proxy approval gate.

- [ ] **Step 1: Run formatting/static checks**

Run: `uv run ruff check src tests`

Expected: exit code 0 with no lint errors.

- [ ] **Step 2: Run the complete automated suite**

Run: `uv run pytest -q`

Expected: exit code 0 and zero failed tests.

- [ ] **Step 3: Verify the generated tagged prompt**

Run:

```powershell
uv run python run_episode.py prompt --run "D:\FINAL REVIEW ANIME\Tam_dang_xu_ly\c640e72b78d3404e9719898998196478"
```

Expected: the prompt names `teamwork-preview`, `goal`, the exact run, the persistent proxy-gate objective, and `operator --run`; it contains no instruction to copy a situation prompt.

- [ ] **Step 4: Migrate the current rejected-proxy run without deleting accepted revisions**

Run:

```powershell
uv run python run_episode.py migrate-run --run "D:\FINAL REVIEW ANIME\Tam_dang_xu_ly\c640e72b78d3404e9719898998196478" --reason autonomous-operator
```

Expected: accepted situation revisions remain present, a new operator revision is prepared, and `next_action.json` points to the one tagged launch rather than a numbered situation.

- [ ] **Step 5: Run one real tagged Antigravity episode through proxy audit**

The user attaches `teamwork-preview` and `goal` and sends the generated prompt once. Antigravity must reach `CHO_NGUOI_DUNG_DUYET_PROXY` without user relay. Verify:

```powershell
$run = "D:\FINAL REVIEW ANIME\Tam_dang_xu_ly\c640e72b78d3404e9719898998196478"
Get-Content "$run\run_state.json"
Get-Content "$run\proxy\loudness_report.json"
Get-Content "$run\accepted_verification\proxy\proxy_audit.json"
ffprobe -v error -show_entries format=duration:stream=codec_type,duration -of json "$run\proxy\review_proxy.mp4"
```

Expected: stage `CHO_NGUOI_DUNG_DUYET_PROXY`; every cue verdict is `MATCH`; START and END boundaries are `CLEAN`; loudness is -15 to -13 LUFS with true peak at most -1.5 dBTP; exactly one video and one audio stream; A/V drift is at most 80 ms.

- [ ] **Step 6: Inspect Git scope and commit any final tested correction**

Run: `git status --short` and `git diff --check`.

Expected: no unplanned files are staged, no whitespace errors exist, and user-owned unrelated changes remain untouched.
