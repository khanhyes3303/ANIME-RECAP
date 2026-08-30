# Antigravity Editorial Ownership and Semantic Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Antigravity the sole episode editor, align every spoken claim to its visual anchor, enforce newcomer-comprehensible storytelling, and require explicit user proxy approval before final publication.

**Architecture:** The engine issues one hashed editor task per situation and accepts Antigravity submissions through an append-only provenance ledger. Cue-level TTS and a deterministic semantic timeline replace back-to-back unit audio; structured character/term introductions and causal chains make newcomer validation measurable. The workflow stops at a user proxy gate, and final rendering is allowed only when approved artifact hashes are unchanged.

**Tech Stack:** Python 3.13, frozen dataclasses, JSON/JSONL artifacts, ffmpeg/ffprobe, pytest, Ruff, uv, existing TikTok/CapCut TTS provider

**Spec:** `docs/superpowers/specs/2026-08-30-antigravity-editorial-ownership-semantic-sync-design.md`

## Global Constraints

- Antigravity is the only author of situation facts, narration, bridges, evidence ranges, visual anchors, character introductions, term explanations, and editorial repairs.
- Codex changes only engine code, schemas, validators, tests, prompts, diagnostics, and workflow behavior; it never edits episode editorial content.
- Gemini Web remains optional and cannot advance the default workflow.
- No dependency, plugin, model, repository, or DLL is installed automatically; missing tools stop with `CAN_CON_NGUOI_XU_LY` and the exact dependency name.
- `CHARACTER_INTRO`, `ACTION`, `REVEAL`, and `OUTCOME` speech may start no more than 100 ms before its mapped visual anchor; the normal visual preroll is 300–1,200 ms.
- Every evidence range contains exactly one semantic event, one action phase, and one story purpose; a four-second homogeneous range is preferred over a ten-second mixed range.
- Source video, rejected proxies, previous finals, and dirty changes in the main checkout are preserved.
- Final render is forbidden until the user explicitly approves a proxy and all approved artifact hashes still match.
- Implement every production behavior through a failing test first; run the focused test red, implement minimally, then run it green.

## File Structure

- Create `src/anime_review_mvp/editor_provenance.py`: editor-task creation, staged acceptance, immutable artifact hashing, atomic ledger updates, and provenance verification.
- Create `src/anime_review_mvp/story_context.py`: character/term introduction registry, causal-chain validation, and episode coherence findings.
- Create `src/anime_review_mvp/semantic_timeline.py`: source-to-program anchor mapping, playback-rate selection, cue scheduling, and lead detection.
- Create `src/anime_review_mvp/cue_audio.py`: ffmpeg command construction for placing cue WAV files at semantic timeline offsets.
- Create `src/anime_review_mvp/proxy_approval.py`: approval manifest creation, hash verification, rejection recording, and final-render guard.
- Modify `src/anime_review_mvp/situations.py`: cue, cue-TTS, story-context, and v2 causal fields while retaining v1 load compatibility.
- Modify `src/anime_review_mvp/jsonio.py`: reusable atomic JSON/JSONL writes.
- Modify `src/anime_review_mvp/tts.py`: synthesize cue WAVs without concatenating them back-to-back.
- Modify `src/anime_review_mvp/adaptive_edl.py`: expose source-to-program mapping and build an EDL whose total includes visual preroll/silence.
- Modify `src/anime_review_mvp/situation_validation.py`: v2 cue/evidence/anchor/newcomer validation.
- Modify `src/anime_review_mvp/local_audit.py`: combine content support, cue timing, coherence, provenance, and technical findings.
- Modify `src/anime_review_mvp/workflow.py`: sequential situation states, Antigravity repair routing, and user proxy gate.
- Modify `src/anime_review_mvp/cli.py`: focused commands that call the new modules; keep orchestration out of the CLI body.
- Modify `src/anime_review_mvp/render.py`: accept only a fully aligned narration WAV and preserve the semantic timeline duration.
- Modify `src/anime_review_mvp/situation_packets.py`: issue one-situation editor packets with task/revision/provenance fields.
- Modify `src/anime_review_mvp/antigravity.py`: enforce the new staged Antigravity write contract.
- Modify `Bo_nao_Antigravity/GEMINI.md`: require per-situation submission and prohibit direct engine-state/artifact writes.
- Add focused unit tests next to each new module and extend `tests/integration/test_situation_pipeline.py` plus a BLACK TORCH timing fixture.

---

### Task 1: Atomic artifact writes and Antigravity provenance ledger

**Files:**
- Create: `src/anime_review_mvp/editor_provenance.py`
- Modify: `src/anime_review_mvp/jsonio.py`
- Test: `tests/unit/test_editor_provenance.py`
- Test: `tests/unit/test_jsonio.py`

**Interfaces:**
- Consumes: existing `MvpError`, `dump_json`, and dataclass-aware `load_json`.
- Produces: `EditorTask`, `AcceptedEditorialRevision`,
  `create_editor_task(run_dir: Path, run_id: str, situation_id: str, revision: int, input_paths: tuple[Path, ...]) -> EditorTask`,
  `accept_antigravity_submission(run_dir: Path, task_id: str, staging_dir: Path) -> AcceptedEditorialRevision`,
  `load_editor_ledger(path: Path) -> tuple[AcceptedEditorialRevision, ...]`,
  `require_antigravity_provenance(run_dir: Path, situation_id: str, artifact_paths: tuple[Path, ...]) -> AcceptedEditorialRevision`,
  `atomic_dump_json(path: Path, value: object) -> None`, and
  `atomic_append_jsonl(path: Path, value: object) -> None`.

- [ ] **Step 1: Write failing atomic-write and ledger tests**

```python
def test_atomic_dump_json_replaces_complete_document(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    atomic_dump_json(path, {"revision": 1})
    atomic_dump_json(path, {"revision": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"revision": 2}
    assert not tuple(tmp_path.glob("*.tmp"))


def test_accept_antigravity_submission_records_engine_owned_provenance(tmp_path: Path) -> None:
    run = tmp_path / "run"
    inputs = (tmp_path / "transcript.json", tmp_path / "frames.json")
    for path in inputs:
        path.write_text(path.name, encoding="utf-8")
    task = create_editor_task(run, "run-001", "situation-001", 1, inputs)
    staging = run / "editor_staging" / task.task_id
    staging.mkdir(parents=True)
    (staging / "situation_draft.json").write_text('{"situation_id":"situation-001"}', encoding="utf-8")
    (staging / "narration_draft.json").write_text('{"situation_id":"situation-001"}', encoding="utf-8")

    accepted = accept_antigravity_submission(run, task.task_id, staging)

    assert accepted.actor == "ANTIGRAVITY"
    assert accepted.task_id == task.task_id
    assert accepted.revision == 1
    assert len(load_editor_ledger(run / "editor_ledger.jsonl")) == 1
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `uv run pytest tests/unit/test_jsonio.py tests/unit/test_editor_provenance.py -q`

Expected: FAIL because `atomic_dump_json`, `EditorTask`, and provenance functions do not exist.

- [ ] **Step 3: Add atomic JSON replacement**

```python
def atomic_dump_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(_to_value(value), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def atomic_append_jsonl(path: Path, value: object) -> None:
    records = [] if not path.is_file() else [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
    ]
    records.append(_to_value(value))
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    os.replace(temporary, path)
```

Use the existing private serializer from `jsonio.py`; do not duplicate dataclass conversion.

- [ ] **Step 4: Implement task and ledger contracts**

```python
@dataclass(frozen=True, slots=True)
class EditorTask:
    task_id: str
    run_id: str
    situation_id: str
    revision: int
    expected_stage: str
    input_sha256: str
    allowed_outputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AcceptedEditorialRevision:
    task_id: str
    run_id: str
    situation_id: str
    revision: int
    actor: str
    input_sha256: str
    situation_sha256: str
    narration_sha256: str
```

`create_editor_task` hashes path names and bytes in a deterministic sorted order, writes
`editor_tasks/task-001.json` for a representative task ID, and permits exactly `situation_draft.json` plus
`narration_draft.json`. `accept_antigravity_submission` rejects unknown/stale tasks,
recomputes the input hash, atomically copies both files into
`accepted_editorial/situation-001/revision-001/`, and atomically rewrites
`editor_ledger.jsonl` with the appended record. Schema-aware merging into episode-level
canonical documents happens only after Task 2 contracts exist. The engine sets the actor
itself; no submitted owner field can set provenance.

- [ ] **Step 5: Add rejection tests for stale inputs and forged ownership**

```python
def test_accept_rejects_changed_editor_inputs(tmp_path: Path) -> None:
    task, run, inputs, staging = prepared_submission(tmp_path)
    inputs[0].write_text("changed", encoding="utf-8")
    with pytest.raises(MvpError, match="EDITOR_INPUT_HASH_CHANGED"):
        accept_antigravity_submission(run, task.task_id, staging)


def test_provenance_ignores_self_declared_owner(tmp_path: Path) -> None:
    task, run, _inputs, staging = prepared_submission(tmp_path)
    (staging / "narration_draft.json").write_text(
        '{"owner":"CODEX","situation_id":"situation-001"}', encoding="utf-8"
    )
    accepted = accept_antigravity_submission(run, task.task_id, staging)
    assert accepted.actor == "ANTIGRAVITY"
```

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/unit/test_jsonio.py tests/unit/test_editor_provenance.py -q`

Expected: PASS.

```powershell
git add src/anime_review_mvp/jsonio.py src/anime_review_mvp/editor_provenance.py tests/unit/test_jsonio.py tests/unit/test_editor_provenance.py
git commit -m "feat: record Antigravity editorial provenance"
```

### Task 2: Cue-level narration and newcomer context contracts

**Files:**
- Modify: `src/anime_review_mvp/situations.py`
- Test: `tests/unit/test_situations.py`

**Interfaces:**
- Consumes: v1 `NarrationPlan`, `NarrationUnit`, and `SituationDocument` loaders.
- Produces: `NarrationClaim`, `NarrationCue`, `SemanticShotUse`, `CueTts`, `CueTtsManifest`, `CharacterContext`, `TermContext`, `StoryContext`, and v2 fields on `EvidenceRange`/`Situation`/`NarrationUnit`/`NarrationPlan`.

- [ ] **Step 1: Write failing contract tests**

```python
def test_v2_narration_requires_visual_anchor_for_every_cue() -> None:
    with pytest.raises(MvpError, match="visual anchor"):
        NarrationCue(
            cue_id="cue-001",
            situation_id="situation-001",
            text="Ông nội Jiro đã đứng chờ sẵn.",
            claim_ids=("claim-001",),
            visual_anchor_source_ms=-1,
            anchor_kind="CHARACTER_INTRO",
            transcript_refs=("transcript-001",),
            frame_refs=("frame-001",),
            shot_ids=("shot-001",),
            introduces_characters=("Ông nội",),
            mentions_characters=("Jiro", "Ông nội"),
            introduces_terms=(),
            mentions_terms=(),
            visual_preroll_ms=500,
            visual_postroll_ms=300,
        )


def test_v1_plan_still_loads_without_cues(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(LEGACY_V1_PLAN_JSON, encoding="utf-8")
    assert load_narration_plan(path).policy_version == "situation-v1"
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `uv run pytest tests/unit/test_situations.py -q`

Expected: FAIL because the new dataclasses and v2 fields do not exist.

- [ ] **Step 3: Add v2 dataclasses with strict invariants**

```python
@dataclass(frozen=True, slots=True)
class NarrationClaim:
    claim_id: str
    text: str
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NarrationCue:
    cue_id: str
    situation_id: str
    text: str
    claim_ids: tuple[str, ...]
    visual_anchor_source_ms: int
    anchor_kind: str
    transcript_refs: tuple[str, ...]
    frame_refs: tuple[str, ...]
    shot_ids: tuple[str, ...]
    introduces_characters: tuple[str, ...]
    mentions_characters: tuple[str, ...]
    introduces_terms: tuple[str, ...]
    mentions_terms: tuple[str, ...]
    visual_preroll_ms: int = 500
    visual_postroll_ms: int = 300


@dataclass(frozen=True, slots=True)
class SemanticShotUse:
    shot_id: str
    semantic_event_id: str
    action_phase: str
    story_purpose: str


@dataclass(frozen=True, slots=True)
class CueTts:
    cue_id: str
    unit_id: str
    wav_path: str
    mp3_path: str
    duration_ms: int
    cache_key: str


@dataclass(frozen=True, slots=True)
class CueTtsManifest:
    cues: tuple[CueTts, ...]
    provider: str
    voice_id: str
    policy_version: str
    cache_hits: int
    cache_misses: int
```

Allow only anchor kinds `SETUP`, `CHARACTER_INTRO`, `CAUSE`, `ACTION`, `REVEAL`,
`OUTCOME`, and `BRIDGE`; require anchor timestamp `>= 0`, preroll `300..1200`, postroll
`0..1200`, nonempty claim/evidence fields, and unique introduction/mention values.

Add `cues: tuple[NarrationCue, ...] = ()` to `NarrationUnit` and
`claims: tuple[NarrationClaim, ...] = ()` to `NarrationPlan`; require both only when
`NarrationPlan.policy_version == "situation-v2"` so v1 JSON remains loadable. Validate
that every cue `claim_ids` value resolves to exactly one plan claim. Add
`cause_or_goal: str = ""` and `audience_summary: str = ""` to `Situation`; v2 validation
makes them mandatory.

Add optional v2 fields to `EvidenceRange`:
`semantic_event_id: str = ""`, `action_phase: str = ""`,
`story_purpose: str = ""`, and `shot_uses: tuple[SemanticShotUse, ...] = ()`. V2 requires
all four. Permit action phases only from `SETUP`, `CAUSE`, `APPROACH`, `ACTION`,
`OUTCOME`, `REACTION`, and `BRIDGE`.

- [ ] **Step 4: Add story-context contracts**

```python
@dataclass(frozen=True, slots=True)
class CharacterContext:
    name: str
    viewer_role: str
    introduced_cue_id: str


@dataclass(frozen=True, slots=True)
class TermContext:
    term: str
    plain_explanation: str
    introduced_cue_id: str


@dataclass(frozen=True, slots=True)
class StoryContext:
    characters: tuple[CharacterContext, ...]
    terms: tuple[TermContext, ...]
    unresolved_threads: tuple[str, ...]
    last_outcome: str
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/unit/test_situations.py -q`

Expected: PASS, including legacy v1 loading.

```powershell
git add src/anime_review_mvp/situations.py tests/unit/test_situations.py
git commit -m "feat: define cue and newcomer context contracts"
```

### Task 3: Newcomer comprehension and causal-chain validation

**Files:**
- Create: `src/anime_review_mvp/story_context.py`
- Modify: `src/anime_review_mvp/situation_validation.py`
- Test: `tests/unit/test_story_context.py`
- Test: `tests/unit/test_situation_validation.py`

**Interfaces:**
- Consumes: `NarrationPlan`, `SituationDocument`, `StoryContext`, and ordered v2 cues.
- Produces: `validate_newcomer_context(plan: NarrationPlan, initial_context: StoryContext) -> StoryContext`,
  `validate_causal_chains(document: SituationDocument) -> None`, and
  `coherence_findings(plan: NarrationPlan, document: SituationDocument) -> tuple[AuditFinding, ...]`.

- [ ] **Step 1: Write failing newcomer tests**

```python
def test_character_cannot_be_used_before_introduction() -> None:
    plan = v2_plan(cues=(cue("cue-001", mentions_characters=("Rago",)),))
    with pytest.raises(MvpError, match="CHARACTER_USED_BEFORE_INTRODUCTION.*Rago"):
        validate_newcomer_context(plan, empty_story_context())


def test_character_can_be_introduced_and_used_in_same_cue() -> None:
    plan = v2_plan(
        cues=(cue("cue-001", introduces_characters=("Rago",), mentions_characters=("Rago",)),)
    )
    context = validate_newcomer_context(plan, empty_story_context())
    assert context.characters[0].name == "Rago"


def test_term_cannot_be_used_before_plain_explanation() -> None:
    plan = v2_plan(cues=(cue("cue-001", mentions_terms=("Hắc Tinh",)),))
    with pytest.raises(MvpError, match="TERM_USED_BEFORE_EXPLANATION.*Hắc Tinh"):
        validate_newcomer_context(plan, empty_story_context())
```

- [ ] **Step 2: Write failing causal and filler tests**

```python
def test_v2_situation_requires_cause_goal_and_audience_summary() -> None:
    document = v2_situations(cause_or_goal="", audience_summary="")
    with pytest.raises(MvpError, match="CAUSAL_CHAIN_INCOMPLETE"):
        validate_causal_chains(document)


def test_repeated_filler_bridge_is_reported() -> None:
    plan = v2_plan_with_bridges(("Tiếp đó.", "Tiếp đó.", "Tiếp đó.", "Tiếp đó."))
    codes = {finding.code for finding in coherence_findings(plan, v2_situations())}
    assert "REPETITIVE_FILLER_BRIDGE" in codes


def test_range_mixing_three_shot_meanings_is_rejected_even_when_only_eight_seconds() -> None:
    source_range = v2_range(
        start_ms=10_000,
        end_ms=18_000,
        semantic_event_id="fight-001-hit",
        action_phase="ACTION",
        story_purpose="Jiro tung cú đánh quyết định.",
        shot_uses=(
            shot_use("shot-001", "fight-001-approach", "APPROACH", "Jiro áp sát."),
            shot_use("shot-002", "fight-001-hit", "ACTION", "Jiro ra đòn."),
            shot_use("shot-003", "fight-001-reaction", "REACTION", "Đám côn đồ hoảng sợ."),
        ),
    )
    with pytest.raises(MvpError, match="SEMANTIC_RANGE_MIXED"):
        validate_semantic_range(source_range)


def test_four_second_range_with_one_meaning_is_accepted() -> None:
    source_range = v2_range(
        start_ms=12_000,
        end_ms=16_000,
        semantic_event_id="fight-001-hit",
        action_phase="ACTION",
        story_purpose="Jiro ra đòn.",
        shot_uses=(
            shot_use("shot-002", "fight-001-hit", "ACTION", "Jiro ra đòn."),
        ),
    )
    validate_semantic_range(source_range)
```

- [ ] **Step 3: Run tests and verify RED**

Run: `uv run pytest tests/unit/test_story_context.py tests/unit/test_situation_validation.py -q`

Expected: FAIL because newcomer/coherence validators do not exist.

- [ ] **Step 4: Implement ordered introduction validation**

Walk cues in plan order. Add `introduces_characters` and `introduces_terms` before checking
the same cue's mentions, so a cue can say “con mèo đen tên Rago” once. Reject duplicate
introductions with conflicting roles/explanations. Return a new immutable `StoryContext`
whose `last_outcome` is the final situation outcome.

- [ ] **Step 5: Implement causal and bridge findings**

For policy v2, require nonempty `setup`, `cause_or_goal`, at least one turning point,
`outcome`, and `audience_summary`. Normalize bridges with Unicode casefold and whitespace.
Report `REPETITIVE_FILLER_BRIDGE` when the same normalized first four words occur three
times consecutively or in more than 25 percent of nonempty bridges. Report
`DUPLICATE_STORY_FACT` when the same normalized factual claim appears in different units.

Implement `validate_semantic_range(source_range: EvidenceRange) -> None`. Require exactly
one `SemanticShotUse` for every declared `shot_id`, reject duplicate/missing/extra shots,
and require every shot-use `semantic_event_id`, `action_phase`, and normalized
`story_purpose` to equal the enclosing range. Raise
`SEMANTIC_RANGE_MIXED: <range_id>: <conflicting shot IDs>` on any mismatch. The failure is
based on semantic labels, never on the number of seconds or shots.

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/unit/test_story_context.py tests/unit/test_situation_validation.py -q`

Expected: PASS.

```powershell
git add src/anime_review_mvp/story_context.py src/anime_review_mvp/situation_validation.py tests/unit/test_story_context.py tests/unit/test_situation_validation.py
git commit -m "feat: validate newcomer story comprehension"
```

### Task 4: Cue-level TTS without back-to-back narration assembly

**Files:**
- Modify: `src/anime_review_mvp/tts.py`
- Test: `tests/unit/test_situation_tts.py`

**Interfaces:**
- Consumes: `NarrationPlan` v2 cues, existing TTS provider/profile/cache, source SHA-256.
- Produces:
  `synthesize_narration_cues(plan: NarrationPlan, output_dir: Path, cache_dir: Path, source_sha256: str, provider: TtsProvider | None = None, converter: Converter = _convert_mp3_to_wav) -> CueTtsManifest`
  and `validate_cue_tts_ids(plan: NarrationPlan, manifest: CueTtsManifest) -> None`.

- [ ] **Step 1: Write a failing cue synthesis test**

```python
def test_v2_tts_synthesizes_each_cue_without_concatenating_narration(tmp_path: Path) -> None:
    plan = v2_plan_with_two_cues("Jiro vừa về nhà.", "Ông nội đã đứng chờ.")
    provider = FakeProvider(durations_ms=(1_200, 1_800))

    manifest = synthesize_narration_cues(
        plan,
        tmp_path / "tts",
        tmp_path / "cache",
        source_sha256="a" * 64,
        provider=provider,
        converter=fake_converter,
    )

    assert [cue.cue_id for cue in manifest.cues] == ["cue-001", "cue-002"]
    assert [cue.duration_ms for cue in manifest.cues] == [1_200, 1_800]
    assert not (tmp_path / "tts" / "narration.wav").exists()
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/test_situation_tts.py::test_v2_tts_synthesizes_each_cue_without_concatenating_narration -q`

Expected: FAIL because `synthesize_narration_cues` does not exist.

- [ ] **Step 3: Implement cue synthesis using existing cache primitives**

Use a cache key over cue text, voice profile, policy version, and source SHA-256. Write
`cue-001.mp3` and `cue-001.wav` for a cue whose ID is `cue-001`; return
`CueTtsManifest`. Do not call
`_concatenate_wavs`. Keep `synthesize_situation_units` unchanged for v1 compatibility.

- [ ] **Step 4: Add cache-hit and ID-order tests**

```python
def test_cue_tts_manifest_order_must_match_plan(tmp_path: Path) -> None:
    manifest = synthesize_fixture_cues(tmp_path, cue_ids=("cue-002", "cue-001"))
    with pytest.raises(MvpError, match="cue IDs must exactly match"):
        validate_cue_tts_ids(v2_plan_with_cue_ids(("cue-001", "cue-002")), manifest)
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/unit/test_situation_tts.py -q`

Expected: PASS.

```powershell
git add src/anime_review_mvp/tts.py tests/unit/test_situation_tts.py
git commit -m "feat: synthesize narration per semantic cue"
```

### Task 5: Semantic timeline and BLACK TORCH voice-ahead regression

**Files:**
- Create: `src/anime_review_mvp/semantic_timeline.py`
- Modify: `src/anime_review_mvp/adaptive_edl.py`
- Create: `tests/fixtures/black_torch_voice_ahead_30s/case.json`
- Test: `tests/unit/test_semantic_timeline.py`
- Test: `tests/unit/test_adaptive_edl.py`
- Test: `tests/integration/test_situation_pipeline.py`

**Interfaces:**
- Consumes: v2 `NarrationPlan`, `CueTtsManifest`, `EditorialPolicy`, and source duration.
- Produces: `CueTiming`, `SemanticTimeline`,
  `build_semantic_timeline(plan: NarrationPlan, tts: CueTtsManifest, source_duration_ms: int, policy: EditorialPolicy) -> tuple[AdaptiveEdlDocument, SemanticTimeline]`,
  `map_source_timestamp(edl: AdaptiveEdlDocument, source_ms: int) -> int`, and
  `semantic_timing_findings(cues: tuple[CueTiming, ...]) -> tuple[AuditFinding, ...]`.

- [ ] **Step 1: Add the confirmed BLACK TORCH fixture**

```json
{
  "unit_id": "unit-004",
  "source_range_start_ms": 229771,
  "source_range_end_ms": 238863,
  "old_program_start_ms": 28728,
  "old_voice_start_ms": 28728,
  "visual_anchor_program_ms": 35786,
  "visual_anchor_source_ms": 236004,
  "cue_duration_ms": 4200,
  "expected_finding": "VOICE_PRECEDES_VISUAL_ANCHOR"
}
```

- [ ] **Step 2: Write failing mapping and regression tests**

```python
def test_black_torch_old_timeline_reports_voice_before_grandfather() -> None:
    case = load_black_torch_voice_ahead_case()
    timing = CueTiming(
        "cue-004-intro-grandfather",
        case["old_voice_start_ms"],
        case["old_voice_start_ms"] + case["cue_duration_ms"],
        case["visual_anchor_program_ms"],
    )
    codes = {finding.code for finding in semantic_timing_findings((timing,))}
    assert codes == {"VOICE_PRECEDES_VISUAL_ANCHOR"}


def test_new_timeline_starts_voice_after_visual_preroll() -> None:
    edl, timeline = build_semantic_timeline(
        black_torch_unit_004_v2(),
        black_torch_unit_004_tts(),
        source_duration_ms=1_400_000,
        policy=EditorialPolicy(),
    )
    cue = timeline.cues[0]
    assert cue.spoken_start_ms >= cue.visual_anchor_program_ms + 300
    assert semantic_timing_findings(timeline.cues) == ()
    assert edl.total_duration_ms >= cue.spoken_end_ms + 300


def test_timeline_keeps_two_semantic_ranges_separate_inside_one_fight() -> None:
    plan = fight_plan_with_approach_and_outcome_ranges()
    edl, timeline = build_semantic_timeline(
        plan, fight_cue_tts(), 60_000, EditorialPolicy()
    )
    assert [segment.range_id for segment in edl.segments] == [
        "range-approach",
        "range-outcome",
    ]
    assert [cue.cue_id for cue in timeline.cues] == [
        "cue-approach",
        "cue-outcome",
    ]
```

- [ ] **Step 3: Run and verify RED**

Run: `uv run pytest tests/unit/test_semantic_timeline.py tests/integration/test_situation_pipeline.py -q`

Expected: FAIL because timeline contracts and functions do not exist.

- [ ] **Step 4: Implement timeline dataclasses and source mapping**

```python
@dataclass(frozen=True, slots=True)
class CueTiming:
    cue_id: str
    spoken_start_ms: int
    spoken_end_ms: int
    visual_anchor_program_ms: int


@dataclass(frozen=True, slots=True)
class SemanticTimeline:
    cues: tuple[CueTiming, ...]
    total_duration_ms: int
```

`map_source_timestamp` finds the adaptive EDL segment containing the source timestamp and
returns `program_start_ms + round((source_ms - segment.source_start_ms) / playback_rate)`.
It rejects anchors in omitted gaps.

- [ ] **Step 5: Implement deterministic per-unit rate selection**

Generate candidate rates from policy minimum to maximum in 0.001 increments and sort by
`(abs(rate - 1.0), rate)`. For each candidate, map every cue anchor, schedule cue start as
`max(anchor + cue.visual_preroll_ms, previous_spoken_end + 80)`, and require the last cue
end plus postroll to fit inside the mapped kept footage. Choose the first valid candidate;
if none fits, raise `MvpError("SEMANTIC_TIMELINE_DOES_NOT_FIT: rewrite narration or select more evidence")`.

Build adaptive segments from the selected rate. The EDL total is visual duration, not sum
of raw cue durations.

- [ ] **Step 6: Implement timing findings**

Return `VOICE_PRECEDES_VISUAL_ANCHOR` when
`spoken_start_ms + 100 < visual_anchor_program_ms`. Include cue ID, both timestamps, and
the measured lead in the finding message.

- [ ] **Step 7: Run tests and commit**

Run: `uv run pytest tests/unit/test_semantic_timeline.py tests/unit/test_adaptive_edl.py tests/integration/test_situation_pipeline.py -q`

Expected: PASS, including the 28.728–35.786 second regression.

```powershell
git add src/anime_review_mvp/semantic_timeline.py src/anime_review_mvp/adaptive_edl.py tests/unit/test_semantic_timeline.py tests/unit/test_adaptive_edl.py tests/integration/test_situation_pipeline.py tests/fixtures/black_torch_voice_ahead_30s/case.json
git commit -m "feat: align narration cues to visual anchors"
```

### Task 6: Build the aligned narration audio track

**Files:**
- Create: `src/anime_review_mvp/cue_audio.py`
- Modify: `src/anime_review_mvp/render.py`
- Test: `tests/unit/test_cue_audio.py`
- Test: `tests/unit/test_render.py`

**Interfaces:**
- Consumes: `CueTtsManifest`, `SemanticTimeline`, output path, ffmpeg runner.
- Produces:
  `build_cue_audio_command(tts: CueTtsManifest, timeline: SemanticTimeline, output: Path) -> list[str]`
  and `render_cue_audio_timeline(tts: CueTtsManifest, timeline: SemanticTimeline, output: Path, runner: Runner = subprocess.run) -> Path`.

- [ ] **Step 1: Write a failing ffmpeg command test**

```python
def test_cue_audio_command_places_each_wav_at_semantic_offset() -> None:
    command = build_cue_audio_command(
        cue_tts_manifest(("cue-001.wav", "cue-002.wav")),
        semantic_timeline(starts=(800, 3_400), total_duration_ms=6_000),
        Path("narration-aligned.wav"),
    )
    graph = command[command.index("-filter_complex") + 1]
    assert "adelay=800|800" in graph
    assert "adelay=3400|3400" in graph
    assert "amix=inputs=3:duration=longest" in graph
    assert "atrim=duration=6.000" in graph
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/test_cue_audio.py -q`

Expected: FAIL because the cue-audio module does not exist.

- [ ] **Step 3: Implement an ffmpeg silence base plus delayed cues**

Build an input 0 silence source such as
`-f lavfi -t 6.000 -i anullsrc=r=44100:cl=mono`, add each cue WAV as a subsequent
input, apply a concrete delay such as `aresample=44100,adelay=800|800`, then mix silence
and cues with `amix`. Finish a six-second fixture with
`atrim=duration=6.000,asetpts=N/SR/TB` and PCM s16le.
Reject overlapping cue timings before invoking ffmpeg.

- [ ] **Step 4: Add duration and missing-file tests**

```python
def test_cue_audio_rejects_missing_wav(tmp_path: Path) -> None:
    with pytest.raises(MvpError, match="cue WAV does not exist"):
        render_cue_audio_timeline(missing_cue_manifest(tmp_path), timeline(), tmp_path / "out.wav")
```

- [ ] **Step 5: Keep final render mapping only the aligned audio input**

Extend existing render tests to assert `build_render_command` maps `1:a:0`, never source
audio, and that rendered duration is compared to `SemanticTimeline.total_duration_ms`.

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/unit/test_cue_audio.py tests/unit/test_render.py -q`

Expected: PASS.

```powershell
git add src/anime_review_mvp/cue_audio.py src/anime_review_mvp/render.py tests/unit/test_cue_audio.py tests/unit/test_render.py
git commit -m "feat: assemble narration on semantic timeline"
```

### Task 7: Local semantic and episode-coherence audit gates

**Files:**
- Modify: `src/anime_review_mvp/local_audit.py`
- Modify: `src/anime_review_mvp/situation_validation.py`
- Test: `tests/unit/test_local_audit.py`
- Test: `tests/unit/test_story_context.py`

**Interfaces:**
- Consumes: accepted provenance, v2 plan/situations, story context, semantic timeline, TTS, EDL, frame evidence, and render result.
- Produces: new finding codes in `EngineAuditReport` and `build_episode_coherence_audit(...)`.

- [ ] **Step 1: Write failing audit tests**

```python
def test_local_audit_fails_when_voice_precedes_visual_anchor() -> None:
    report = build_v2_local_audit(
        timeline=timeline(cue_start_ms=1_000, visual_anchor_ms=6_000)
    )
    assert report.passed is False
    assert "VOICE_PRECEDES_VISUAL_ANCHOR" in {finding.code for finding in report.findings}


def test_local_audit_requires_antigravity_provenance() -> None:
    report = build_v2_local_audit(provenance=())
    assert "EDITOR_PROVENANCE_INVALID" in {finding.code for finding in report.findings}


def test_episode_audit_rejects_unintroduced_rago_and_repetitive_bridges() -> None:
    report = build_episode_coherence_audit(unintroduced_rago_fixture())
    assert {"CHARACTER_USED_BEFORE_INTRODUCTION", "REPETITIVE_FILLER_BRIDGE"} <= {
        finding.code for finding in report.findings
    }


def test_local_audit_rejects_semantically_mixed_evidence_range() -> None:
    report = build_v2_local_audit(plan=plan_with_mixed_fight_range())
    assert "SEMANTIC_RANGE_MIXED" in {finding.code for finding in report.findings}
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/test_local_audit.py tests/unit/test_story_context.py -q`

Expected: FAIL because v2 audit inputs and findings are not wired.

- [ ] **Step 3: Integrate deterministic semantic findings**

For v2 reports, require provenance for every situation, exact cue ID agreement across
plan/TTS/timeline, no timing findings, newcomer validation success, no coherence findings,
and render duration within 80 ms of semantic timeline total. Keep v1 behavior unchanged
for legacy fixtures.

- [ ] **Step 4: Ensure repair reports name exact cue and timestamps**

Assert that `VOICE_PRECEDES_VISUAL_ANCHOR` evidence contains cue ID, spoken start, visual
anchor, lead milliseconds, source frame refs, and program frame refs. Do not reduce this
to unit-level PASS/FAIL.

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/unit/test_local_audit.py tests/unit/test_story_context.py -q`

Expected: PASS.

```powershell
git add src/anime_review_mvp/local_audit.py src/anime_review_mvp/situation_validation.py tests/unit/test_local_audit.py tests/unit/test_story_context.py
git commit -m "feat: fail closed on semantic and coherence errors"
```

### Task 8: Sequential Antigravity workflow and user proxy approval state

**Files:**
- Modify: `src/anime_review_mvp/workflow.py`
- Test: `tests/unit/test_workflow.py`

**Interfaces:**
- Consumes: existing persisted `RunState` with legacy schema upgrade.
- Produces: new stages, `begin_editor_task(...)`, `accept_editor_revision(...)`, `lock_editor_situation(...)`, `route_editor_repair(...)`, `approve_proxy_state(...)`, and `reject_proxy_state(...)`.

- [ ] **Step 1: Write the failing state-path test**

```python
def test_v2_path_processes_one_situation_then_waits_for_user_proxy_approval(tmp_path: Path) -> None:
    run = tmp_path / "run"
    new_state(run)
    path = (
        (Stage.CHUAN_BI, Stage.TRICH_XUAT_BANG_CHUNG),
        (Stage.TRICH_XUAT_BANG_CHUNG, Stage.CHO_ANTIGRAVITY_TINH_HUONG),
        (Stage.CHO_ANTIGRAVITY_TINH_HUONG, Stage.KIEM_DINH_TINH_HUONG),
        (Stage.KIEM_DINH_TINH_HUONG, Stage.TAO_TTS_TINH_HUONG),
        (Stage.TAO_TTS_TINH_HUONG, Stage.LAP_TIMELINE_TINH_HUONG),
        (Stage.LAP_TIMELINE_TINH_HUONG, Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG),
    )
    for expected, target in path:
        advance(run, expected, target)
    lock_editor_situation(run, "situation-001", next_situation_id="")
    advance(run, Stage.KIEM_DINH_MACH_TRUYEN_TOAN_TAP, Stage.DUNG_PROXY)
    advance(run, Stage.DUNG_PROXY, Stage.KIEM_DINH_PROXY)
    advance(run, Stage.KIEM_DINH_PROXY, Stage.CHO_NGUOI_DUNG_DUYET_PROXY)
    assert read_state(run).stage is Stage.CHO_NGUOI_DUNG_DUYET_PROXY
```

- [ ] **Step 2: Write failing ownership and final-gate tests**

```python
def test_content_repair_routes_to_antigravity_not_codex(tmp_path: Path) -> None:
    run = run_at_semantic_audit(tmp_path)
    state = route_editor_repair(run, ("situation-004",), ("VOICE_PRECEDES_VISUAL_ANCHOR",), "a" * 64)
    assert state.stage is Stage.CHO_ANTIGRAVITY_TINH_HUONG
    assert state.current_situation_id == "situation-004"


def test_final_render_is_forbidden_before_user_approval(tmp_path: Path) -> None:
    run = run_at_proxy_wait(tmp_path)
    with pytest.raises(MvpError, match="proxy approval"):
        advance(run, Stage.CHO_NGUOI_DUNG_DUYET_PROXY, Stage.DUNG_VIDEO_CUOI)
```

- [ ] **Step 3: Run and verify RED**

Run: `uv run pytest tests/unit/test_workflow.py -q`

Expected: FAIL because the v2 stages and gates do not exist.

- [ ] **Step 4: Add v2 stages and state fields**

Add stages from the approved spec and fields:

```python
editor_task_id: str = ""
editorial_revision: int = 0
approved_proxy_sha256: str = ""
approved_artifact_sha256: str = ""
proxy_rejection_note: str = ""
```

Upgrade legacy state JSON by defaulting missing fields. Keep legacy transitions only for
already-existing v1 runs. New v2 repair records always use owner `ANTIGRAVITY`; never
target `CODEX_BIEN_TAP`.

- [ ] **Step 5: Require explicit approval token in transition**

Extend `advance` with private `_proxy_approval_verified: bool = False`, and permit
`CHO_NGUOI_DUNG_DUYET_PROXY -> DUNG_VIDEO_CUOI` only when it is true. Do not expose a CLI
flag that sets this boolean directly; `proxy_approval.py` calls it after hash verification.

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/unit/test_workflow.py -q`

Expected: PASS, with legacy schema tests still green.

```powershell
git add src/anime_review_mvp/workflow.py tests/unit/test_workflow.py
git commit -m "feat: gate final render on user-approved proxy"
```

### Task 9: Proxy approval manifest and approved-hash final guard

**Files:**
- Create: `src/anime_review_mvp/proxy_approval.py`
- Test: `tests/unit/test_proxy_approval.py`

**Interfaces:**
- Consumes: proxy path, plan, situations, story context, semantic timeline, current run state.
- Produces: `ProxyApproval`,
  `approve_proxy(run_dir: Path, proxy_path: Path, editorial_paths: tuple[Path, ...], now_utc: Clock = utc_now) -> ProxyApproval`,
  `reject_proxy(run_dir: Path, note: str, situation_ids: tuple[str, ...], now_utc: Clock = utc_now) -> RunState`, and
  `require_approved_artifacts(run_dir: Path, editorial_paths: tuple[Path, ...]) -> ProxyApproval`.

- [ ] **Step 1: Write failing approval tests**

```python
def test_approve_proxy_records_proxy_and_editorial_hashes(tmp_path: Path) -> None:
    run, artifacts = prepared_proxy_run(tmp_path)
    approval = approve_proxy(run, artifacts.proxy, artifacts.editorial_paths)
    assert approval.proxy_sha256 == sha256_file(artifacts.proxy)
    assert approval.editorial_sha256 == content_sha256(artifacts.editorial_paths)
    assert read_state(run).stage is Stage.DUNG_VIDEO_CUOI


def test_final_guard_rejects_changed_narration_after_approval(tmp_path: Path) -> None:
    run, artifacts = approved_proxy_run(tmp_path)
    artifacts.plan.write_text("changed", encoding="utf-8")
    with pytest.raises(MvpError, match="APPROVED_ARTIFACT_HASH_CHANGED"):
        require_approved_artifacts(run, artifacts.editorial_paths)


def test_rejection_preserves_proxy_and_routes_note_to_antigravity(tmp_path: Path) -> None:
    run, artifacts = prepared_proxy_run(tmp_path)
    rejected = reject_proxy(run, "Voice nói ông nội trước hình.", ("situation-004",))
    assert artifacts.proxy.exists()
    assert rejected.stage is Stage.CHO_ANTIGRAVITY_TINH_HUONG
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/test_proxy_approval.py -q`

Expected: FAIL because proxy approval does not exist.

- [ ] **Step 3: Implement approval and rejection manifests**

Write `proxy_approval.json` atomically with run ID, revision, proxy SHA-256, combined hashes
for situations/plan/context/timeline/EDL/TTS, and approval timestamp supplied by an injected
clock. Rejection of revision 2 writes `proxy_rejections/revision-002.json`, never modifies the proxy, and
invalidates only affected plus downstream situation artifacts.

- [ ] **Step 4: Run tests and commit**

Run: `uv run pytest tests/unit/test_proxy_approval.py -q`

Expected: PASS.

```powershell
git add src/anime_review_mvp/proxy_approval.py tests/unit/test_proxy_approval.py
git commit -m "feat: preserve and verify user proxy approval"
```

### Task 10: One-situation Antigravity packet and operator contract

**Files:**
- Modify: `src/anime_review_mvp/situation_packets.py`
- Modify: `src/anime_review_mvp/antigravity.py`
- Modify: `Bo_nao_Antigravity/GEMINI.md`
- Test: `tests/unit/test_situation_packets.py`
- Test: `tests/unit/test_antigravity_contract.py`

**Interfaces:**
- Consumes: `EditorTask`, one situation's evidence, accepted `StoryContext`, and prior outcome.
- Produces: `build_situation_editor_packet(...)` scoped to one situation and a prompt that writes only the task staging directory.

- [ ] **Step 1: Write failing packet tests**

```python
def test_editor_packet_contains_exact_task_and_one_situation() -> None:
    packet = build_situation_editor_packet(
        task=editor_task("task-001", "situation-004", 2),
        source=SOURCE,
        transcript=TRANSCRIPT,
        shots=SHOTS,
        frame_manifest_path=FRAMES,
        policy=POLICY,
        prior_context=STORY_CONTEXT,
    )
    assert packet.task_id == "task-001"
    assert packet.situation_id == "situation-004"
    assert packet.revision == 2
    assert packet.required_outputs == ("situation_draft.json", "narration_draft.json")


def test_prompt_forbids_codex_editor_and_direct_engine_writes() -> None:
    prompt = render_situation_editor_prompt(packet_fixture())
    assert "Antigravity là biên tập viên duy nhất" in prompt
    assert "không ghi run_state.json" in prompt
    assert "không ghi trực tiếp TTS" in prompt
    assert "visual_anchor_source_ms" in prompt
    assert "người chưa biết anime" in prompt
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/test_situation_packets.py tests/unit/test_antigravity_contract.py -q`

Expected: FAIL because the packet still targets whole-episode outputs and has no task provenance.

- [ ] **Step 3: Restrict packet and write policy**

Replace whole-episode `required_outputs` with exactly the two staging filenames. Include
task ID, revision, situation ID, input hash, story context, allowed staging directory,
schema examples for v2 cues and per-shot semantic-use labels, and the
`accept-antigravity` next command. Reject prompts
that mention Codex as a content repair owner.

- [ ] **Step 4: Rewrite GEMINI policy around the engine boundary**

Require Antigravity to author one situation, submit staging artifacts, run the engine's
TTS/timeline/semantic checks, and respond to exact repair codes. Clarify that “tạo TTS và
khớp hình” means invoking engine commands and revising editorial inputs, not writing TTS,
EDL, state, PASS reports, or source code directly. Preserve the no-install rule.
Require Antigravity to split a range whenever adjacent shots differ in small event,
action phase, or story purpose, even inside the same fight or conversation. Explicitly
prefer a short homogeneous range to a longer mixed range.

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/unit/test_situation_packets.py tests/unit/test_antigravity_contract.py -q`

Expected: PASS.

```powershell
git add src/anime_review_mvp/situation_packets.py src/anime_review_mvp/antigravity.py Bo_nao_Antigravity/GEMINI.md tests/unit/test_situation_packets.py tests/unit/test_antigravity_contract.py
git commit -m "feat: make Antigravity the sole situation editor"
```

### Task 11: CLI orchestration and final publication guard

**Files:**
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `run_episode.py`
- Test: `tests/unit/test_cli_situations.py`
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: all modules from Tasks 1–10.
- Produces CLI commands `migrate-run`, `editor-task`, `accept-antigravity`, `tts --situation`, `timeline --situation`, `audit --phase situation|episode|proxy|engine`, `approve-proxy`, `reject-proxy`, and guarded `render --quality final`.

- [ ] **Step 1: Write failing CLI parser and gate tests**

```python
def test_cli_exposes_editor_and_proxy_commands() -> None:
    parser = cli._parser()
    assert parser.parse_args(["migrate-run", "--run", "run", "--reason", "user-rejected"]).command == "migrate-run"
    assert parser.parse_args(["editor-task", "--run", "run"]).command == "editor-task"
    assert parser.parse_args(["approve-proxy", "--run", "run"]).command == "approve-proxy"
    assert parser.parse_args([
        "reject-proxy", "--run", "run", "--note", "Voice sớm", "--situation", "situation-004"
    ]).command == "reject-proxy"


def test_cli_final_render_refuses_unapproved_proxy(tmp_path: Path) -> None:
    run = prepared_unapproved_proxy_run(tmp_path)
    with pytest.raises(MvpError, match="proxy approval"):
        cli._render(run, "final")
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/test_cli_situations.py -q`

Expected: FAIL because the commands and approval guard do not exist.

- [ ] **Step 3: Add thin CLI handlers**

Each handler resolves paths, loads artifacts, calls one focused module function, writes
`next_action.json`, and prints the produced artifact path. Keep hash logic, validation,
timeline scheduling, and approval decisions out of `cli.py`.

`migrate-run --reason user-rejected` is the only command allowed to reopen a completed v1
run. It first copies the existing plan, EDL, TTS manifests, proxy, audit reports, and final
into `revisions/revision-001/`, verifies those copies, increments `editorial_revision` to
2, clears only approval/lock fields derived from revision 1, and enters
`CHO_ANTIGRAVITY_TINH_HUONG`. It never deletes or overwrites the published revision-1
files.

Expected examples:

```powershell
uv run python run_episode.py editor-task --run RUN_DIR
uv run python run_episode.py migrate-run --run RUN_DIR --reason user-rejected
uv run python run_episode.py accept-antigravity --run RUN_DIR --task TASK_ID --input STAGING_DIR
uv run python run_episode.py tts --run RUN_DIR --situation situation-004
uv run python run_episode.py timeline --run RUN_DIR --situation situation-004
uv run python run_episode.py audit --run RUN_DIR --phase situation
uv run python run_episode.py approve-proxy --run RUN_DIR
uv run python run_episode.py reject-proxy --run RUN_DIR --note "Voice nói trước hình" --situation situation-004
```

- [ ] **Step 4: Guard final render and engine completion**

Before final render, call `require_approved_artifacts`; before publication, compare final
inputs to the approval manifest again. Engine audit must verify the final render hash,
approved revision, and semantic report before calling `advance(..., _engine_audit_passed=True)`.

- [ ] **Step 5: Make next-action output explicit for nontechnical users**

At `CHO_NGUOI_DUNG_DUYET_PROXY`, write the proxy path and exactly two commands:
`approve-proxy` and `reject-proxy` with a plain-language note. Never auto-approve.

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/test_cli_situations.py -q`

Expected: PASS.

```powershell
git add src/anime_review_mvp/cli.py run_episode.py tests/unit/test_cli.py tests/unit/test_cli_situations.py
git commit -m "feat: orchestrate sequential editor and proxy approval"
```

### Task 12: End-to-end v2 integration and legacy compatibility

**Files:**
- Modify: `tests/integration/test_situation_pipeline.py`
- Modify: `tests/unit/test_cli_situations.py`
- Modify: `tests/unit/test_workflow.py`
- Modify: `docs/gemini-web-smoke.md`
- Create: `docs/antigravity-editorial-runbook.md`

**Interfaces:**
- Consumes: complete v2 workflow.
- Produces: a deterministic end-to-end fixture proving per-situation acceptance through user proxy gate, plus a user-facing runbook.

- [ ] **Step 1: Write the failing end-to-end test**

```python
def test_v2_episode_requires_antigravity_semantic_sync_and_user_approval(tmp_path: Path) -> None:
    run = prepare_two_situation_run(tmp_path)
    submit_and_accept_antigravity_situation(run, "situation-001")
    synthesize_schedule_and_lock(run, "situation-001")
    submit_and_accept_antigravity_situation(run, "situation-002")
    synthesize_schedule_and_lock(run, "situation-002")
    build_episode_proxy(run)

    assert read_state(run).stage is Stage.CHO_NGUOI_DUNG_DUYET_PROXY
    with pytest.raises(MvpError, match="proxy approval"):
        render_final(run)

    approve_proxy(run, proxy_path(run), approved_editorial_paths(run))
    final = render_and_audit_final(run)
    assert final.is_file()
    assert read_state(run).stage is Stage.HOAN_THANH
```

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest tests/integration/test_situation_pipeline.py -q`

Expected: FAIL until all v2 CLI/workflow pieces are connected.

- [ ] **Step 3: Complete integration wiring without weakening assertions**

Use fake TTS and fake ffmpeg runners only at external boundaries. Exercise real task
hashing, provenance acceptance, newcomer validation, semantic scheduling, repair routing,
proxy approval hashes, and final guard.

- [ ] **Step 4: Prove v1 fixtures remain readable and Gemini stays optional**

Run: `uv run pytest tests/unit/test_situations.py tests/unit/test_workflow.py tests/unit/test_gemini_packets.py tests/unit/test_gemini_session.py -q`

Expected: PASS. Existing v1 runs can be inspected/resumed, but new default runs use v2 and
contain no Gemini stage.

- [ ] **Step 5: Write the operator runbook**

Document the exact lifecycle: prepare evidence, issue one task, let Antigravity submit,
run TTS/timeline/audit, repair only the failed situation, build proxy, ask the user to
approve/reject, then render final. Include the no-install stop rule and explain that Codex
must never edit episode narration.

- [ ] **Step 6: Run focused integration tests and commit**

Run: `uv run pytest tests/integration/test_situation_pipeline.py tests/unit/test_cli_situations.py tests/unit/test_workflow.py -q`

Expected: PASS.

```powershell
git add tests/integration/test_situation_pipeline.py tests/unit/test_cli_situations.py tests/unit/test_workflow.py docs/gemini-web-smoke.md docs/antigravity-editorial-runbook.md
git commit -m "test: prove Antigravity-owned semantic workflow"
```

### Task 13: Full verification and BLACK TORCH revision-2 handoff

**Files:**
- Runtime only: `Tam_dang_xu_ly/c640e72b78d3404e9719898998196478/`
- Runtime only: `Kho_Anime/BLACK TORCH/Mua_01/Tap_001/`
- No episode narration or evidence-range edits by Codex.

**Interfaces:**
- Consumes: verified v2 engine and existing BLACK TORCH source evidence.
- Produces: preserved rejected revision 1, a revision-2 Antigravity task, and a proxy awaiting user approval.

- [ ] **Step 1: Run full static and automated verification**

Run: `uv run ruff check src tests run_episode.py`

Expected: `All checks passed!`

Run: `uv run pytest -q`

Expected: all tests PASS with zero failures.

- [ ] **Step 2: Preserve revision 1 and reopen the run**

Run the new rejection command using the user's real note:

```powershell
uv run python run_episode.py migrate-run --run "D:\FINAL REVIEW ANIME\Tam_dang_xu_ly\c640e72b78d3404e9719898998196478" --reason user-rejected --note "Voice nói ông nội trước hình khoảng 5 giây; lời kể khó hiểu với người mới"
```

Expected: the old final/proxy remain present, revision increments to 2, and state becomes
`CHO_ANTIGRAVITY_TINH_HUONG` at `situation-001`.

- [ ] **Step 3: Generate the first revision-2 Antigravity task**

Run:

```powershell
uv run python run_episode.py editor-task --run "D:\FINAL REVIEW ANIME\Tam_dang_xu_ly\c640e72b78d3404e9719898998196478"
```

Expected: an artifact such as `editor_tasks/task-7a30f48f.json`, a staging directory, and
`PROMPT_GUI_ANTIGRAVITY.txt` are produced. Codex does not open or edit the two draft JSON
outputs.

- [ ] **Step 4: Let Antigravity process every situation sequentially**

For each emitted task, Antigravity reads the packet, writes the two staging files, submits
them with `accept-antigravity`, invokes the emitted TTS/timeline/audit command, and repairs
only reported cues. Stop immediately and tell the user if any required tool is missing;
do not install it.

- [ ] **Step 5: Verify the new proxy before user handoff**

Run: `ffprobe -v error -show_entries stream=index,codec_type,duration,start_time -show_entries format=duration,size -of json PROXY_PATH`

Run: `crv "PROXY_PATH" -o "RUN_DIR\crv_revision_2_proxy" --grid --max-frames 60 --no-transcribe --why "Kiểm tra mạch kể cho người mới và voice không nói trước hình"`

Expected: local/episode/proxy audits pass, state is `CHO_NGUOI_DUNG_DUYET_PROXY`, the
grandfather cue starts at or after its visual anchor, every range passes semantic
homogeneity validation, and no final publication has run.

- [ ] **Step 6: Stop for explicit user proxy approval**

Open the proxy for the user and report its absolute path. Do not run `approve-proxy` or
render final until the user explicitly approves this revision.
