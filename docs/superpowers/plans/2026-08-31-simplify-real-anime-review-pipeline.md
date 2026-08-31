# Simplify Real Anime Review Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing Antigravity review flow execute from the correct checkout, fit every cue to its own evidence range, reject fake semantic verification, and expose six simple public stages.

**Architecture:** Keep the internal recovery state machine, accepted artifacts, TTS, renderer, and local audit. Add a fail-closed run/code identity boundary, change semantic timing from one rate per situation unit to one rate per cue evidence range, require the measured machine audit at semantic acceptance, and project internal states to a small user-facing stage vocabulary.

**Tech Stack:** Python 3.12, frozen dataclasses, JSON artifacts, pytest, uv, FFmpeg/FFprobe runners (mocked in tests)

**Spec:** `docs/superpowers/specs/2026-08-31-simplify-real-anime-review-pipeline-design.md`

## Global Constraints

- Do not call Antigravity, a network TTS provider, or render the real episode while developing or testing.
- Production proxy duration is 420,000–720,000 ms; preferred duration is 480,000–600,000 ms.
- Leading, inter-cue, and trailing narration silence must never exceed 1,200 ms.
- Codex changes engine, schema, validators, and tests only; it does not write review narration or choose anime scenes.
- Existing internal revision/ledger data remains readable, but it cannot substitute for measured technical evidence.
- Every task uses test-first development and an independently reviewable commit.

---

### Task 1: Fail-closed run/code identity

**Files:**
- Create: `src/anime_review_mvp/run_identity.py`
- Modify: `src/anime_review_mvp/workflow.py:74-292`
- Modify: `src/anime_review_mvp/cli.py:300-380`
- Test: `tests/unit/test_run_identity.py`
- Test: `tests/unit/test_workflow.py`

**Interfaces:**
- Produces: `RunCodeIdentity(repository_root: str, git_commit: str, contract_version: str)`.
- Produces: `capture_run_code_identity(path: Path, runner: Runner = subprocess.run) -> RunCodeIdentity`.
- Produces: `validate_run_code_identity(run_dir: Path, recorded: RunCodeIdentity, engine_root: Path | None = None, runner: Runner = subprocess.run) -> None`.
- `RunState` gains optional persisted fields `repository_root`, `code_commit`, and `contract_version`; legacy states remain readable.

- [ ] **Step 1: Write failing identity tests**

```python
def test_identity_rejects_engine_from_another_checkout(tmp_path: Path) -> None:
    run = tmp_path / "repo-a" / "Tam_dang_xu_ly" / "run-1"
    recorded = RunCodeIdentity(str(tmp_path / "repo-a"), "a" * 40, "anime-review-v3")
    with pytest.raises(MvpError, match="RUN_CODE_IDENTITY_MISMATCH"):
        validate_run_code_identity(run, recorded, engine_root=tmp_path / "repo-b")


def test_identity_rejects_wrong_commit_in_same_checkout(tmp_path: Path) -> None:
    recorded = RunCodeIdentity(str(tmp_path), "a" * 40, "anime-review-v3")
    with pytest.raises(MvpError, match="RUN_CODE_IDENTITY_MISMATCH"):
        validate_run_code_identity(
            tmp_path / "run",
            recorded,
            engine_root=tmp_path,
            runner=lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="b" * 40),
        )
```

- [ ] **Step 2: Run the identity tests and confirm RED**

Run: `uv run pytest tests/unit/test_run_identity.py -q`
Expected: FAIL because `anime_review_mvp.run_identity` does not exist.

- [ ] **Step 3: Implement identity capture and validation**

```python
@dataclass(frozen=True, slots=True)
class RunCodeIdentity:
    repository_root: str
    git_commit: str
    contract_version: str = "anime-review-v3"


def validate_run_code_identity(run_dir, recorded, *, engine_root=None, runner=subprocess.run):
    actual_root = (engine_root or Path(__file__).resolve().parents[2]).resolve()
    expected_root = Path(recorded.repository_root).resolve()
    if actual_root != expected_root:
        raise MvpError("RUN_CODE_IDENTITY_MISMATCH")
    completed = runner(
        ["git", "-C", str(actual_root), "merge-base", "--is-ancestor", recorded.git_commit, "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise MvpError("RUN_CODE_IDENTITY_MISMATCH")
```

Persist the captured identity in `new_state()`. In `cli._episode()`, validate it before returning state or changing any artifact. For a legacy state without identity, discover the repository containing `run_dir`; only migrate it when that repository equals the engine repository, otherwise raise `RUN_CODE_IDENTITY_MISMATCH`.

- [ ] **Step 4: Use absolute repository commands in generated prompts**

Change `_autonomous_task_prompt()` to render both continuation commands with the absolute `run_episode.py` path derived from the validated repository root:

```python
entrypoint = Path(state.repository_root) / "run_episode.py"
f'uv run python "{entrypoint}" {accept_command}'
f'uv run python "{entrypoint}" operator --run "{resolved_run}"'
```

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `uv run pytest tests/unit/test_run_identity.py tests/unit/test_workflow.py tests/unit/test_cli_antigravity.py -q`
Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```powershell
git add src/anime_review_mvp/run_identity.py src/anime_review_mvp/workflow.py src/anime_review_mvp/cli.py tests/unit/test_run_identity.py tests/unit/test_workflow.py tests/unit/test_cli_antigravity.py
git commit -m "fix: bind review runs to their engine checkout"
```

### Task 2: Fit one cue to one evidence range

**Files:**
- Modify: `src/anime_review_mvp/semantic_timeline.py:53-166`
- Modify: `src/anime_review_mvp/cli.py:2845-2870`
- Modify: `src/anime_review_mvp/situation_packets.py:175-205`
- Test: `tests/unit/test_semantic_timeline.py`
- Test: `tests/integration/test_situation_pipeline.py`

**Interfaces:**
- Produces: `select_cue_source_window(evidence: EvidenceRange, cue: NarrationCue, shots: ShotDocument, required_program_ms: int, policy: EditorialPolicy) -> CueSourceWindow`.
- Produces: `CueSourceWindow(source_start_ms: int, source_end_ms: int, playback_rate: float, shot_ids: tuple[str, ...])`.
- `build_semantic_timeline(plan, tts, source_duration_ms, policy, shots: ShotDocument | None = None)` keeps its return types; production callers pass the run's measured `ShotDocument`.
- A cue that cannot fit returns an `MvpError` beginning with `CUE_TIMELINE_DOES_NOT_FIT` and includes cue ID, evidence duration, voice duration, and legal rate interval.

- [ ] **Step 1: Write failing per-cue timing tests**

```python
def test_each_cue_range_gets_its_own_playback_rate() -> None:
    plan = _plan_with_ranges((3_000, 6_000), cue_voice_ms=(2_000, 4_000))
    edl, timeline = build_semantic_timeline(
        plan,
        _tts_for((2_000, 4_000)),
        source_duration_ms=20_000,
        policy=EditorialPolicy(target_minimum_ms=1_000, target_maximum_ms=60_000),
        shots=_shots_for_plan(plan),
    )
    assert edl.segments[0].playback_rate != edl.segments[1].playback_rate
    assert max(
        following.spoken_start_ms - current.spoken_end_ms
        for current, following in pairwise(timeline.cues)
    ) <= 1_200


def test_277_seconds_voice_cannot_approve_764_seconds_evidence() -> None:
    with pytest.raises(MvpError, match="CUE_TIMELINE_DOES_NOT_FIT|SEMANTIC_TIMELINE_DURATION_INVALID"):
        build_semantic_timeline(
            _single_cue_plan(evidence_ms=764_000),
            _single_cue_tts(voice_ms=277_000),
            source_duration_ms=900_000,
            policy=EditorialPolicy(),
            shots=_single_shot_document(duration_ms=764_000),
        )
```

- [ ] **Step 2: Run timing tests and confirm RED**

Run: `uv run pytest tests/unit/test_semantic_timeline.py -q`
Expected: the per-cue rate test fails because rates are currently selected once per unit.

- [ ] **Step 3: Implement per-range rate selection**

Replace `_unit_segments()` and the unit-wide candidate loop with a cue/range loop. Resolve each cue through `cue_evidence_range()`, compute `required_program_ms = preroll + voice_ms + postroll`, then enumerate contiguous windows formed only from the cue's Antigravity-approved `shot_ids`. A valid window must contain the visual anchor, stay inside the accepted evidence range, and fit at a legal playback rate. Choose the valid window whose rate is closest to 1.0; this permits trimming only at measured boundaries of shots Antigravity already selected.

```python
@dataclass(frozen=True, slots=True)
class CueSourceWindow:
    source_start_ms: int
    source_end_ms: int
    playback_rate: float
    shot_ids: tuple[str, ...]


def _legal_rate(source_ms, required_program_ms, policy):
    rate = source_ms / required_program_ms
    return round(rate, 3) if policy.minimum_playback_rate <= rate <= policy.maximum_playback_rate else None
```

Never cut inside a shot and never add a shot not listed by the cue. If no approved contiguous shot window fits, return `CUE_TIMELINE_DOES_NOT_FIT`; the error routes only that cue back to Antigravity.

Update `_timeline_command()` to load `run_dir / "shots.json"` and pass it to `build_semantic_timeline()`. Existing unit fixtures may omit `shots` only when each evidence range already fits without trimming.

- [ ] **Step 4: Make the repair prompt actionable**

Update the situation editor prompt to state that each cue must have its own compact range and to include the returned evidence/voice durations. Do not ask Antigravity to rewrite unrelated situations.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `uv run pytest tests/unit/test_semantic_timeline.py tests/unit/test_situation_packets.py tests/integration/test_situation_pipeline.py -q`
Expected: PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/anime_review_mvp/semantic_timeline.py src/anime_review_mvp/situation_packets.py tests/unit/test_semantic_timeline.py tests/unit/test_situation_packets.py tests/integration/test_situation_pipeline.py
git commit -m "fix: fit every review cue to its own scene range"
```

### Task 3: Make the measured machine audit non-overridable

**Files:**
- Modify: `src/anime_review_mvp/cli.py:628-680,2309-2375`
- Modify: `src/anime_review_mvp/local_audit.py:189-270`
- Test: `tests/unit/test_local_audit.py`
- Test: `tests/unit/test_cli_antigravity.py`

**Interfaces:**
- Produces: `require_current_proxy_machine_pass(run_dir: Path, episode: Path) -> EngineAuditReport`.
- Semantic verifier acceptance calls this function immediately before accepting `proxy_audit_draft.json`.

- [ ] **Step 1: Write failing non-override tests**

```python
def test_proxy_match_cannot_override_failed_machine_audit(tmp_path: Path) -> None:
    run, episode = _proxy_verifier_run(tmp_path, duration_ms=764_000)
    _write_all_match_proxy_audit(run)
    with pytest.raises(MvpError, match="PROXY_MACHINE_AUDIT_REQUIRED"):
        cli._accept_verifier(run, "__episode__-revision-001", run / "staging")
    assert read_state(run).stage is Stage.CHO_ANTIGRAVITY_KIEM_DINH_PROXY
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `uv run pytest tests/unit/test_local_audit.py tests/unit/test_cli_antigravity.py -q`
Expected: acceptance advances despite the failed/stale machine audit.

- [ ] **Step 3: Recompute the machine gate at acceptance**

Extract the existing `build_v2_local_audit()` load/call sequence into `require_current_proxy_machine_pass()`. It reloads current plan, situations, timeline, TTS, EDL, render result, provenance, context, and loudness report. If `report.passed` is false, raise `MvpError("PROXY_MACHINE_AUDIT_REQUIRED: " + ",".join(codes))` before copying or accepting the semantic audit.

- [ ] **Step 4: Verify duration, silence, loudness, streams, and drift remain objective gates**

Extend `test_local_audit.py` with one failing test per objective finding code: `PRODUCTION_DURATION_OUT_OF_RANGE`, `NARRATION_GAP_TOO_LONG`, `NARRATION_LOUDNESS_OUT_OF_RANGE`, `STREAM_COUNT_INVALID`, and `RENDER_DRIFT`.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `uv run pytest tests/unit/test_local_audit.py tests/unit/test_cli_antigravity.py tests/integration/test_autonomous_operator.py -q`
Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```powershell
git add src/anime_review_mvp/cli.py src/anime_review_mvp/local_audit.py tests/unit/test_local_audit.py tests/unit/test_cli_antigravity.py tests/integration/test_autonomous_operator.py
git commit -m "fix: keep machine proxy failures non-overridable"
```

### Task 4: Reject fabricated semantic verifier output

**Files:**
- Modify: `src/anime_review_mvp/review_packets.py:183-242`
- Modify: `src/anime_review_mvp/review_contracts.py:13-135`
- Test: `tests/unit/test_review_packets.py`
- Test: `tests/unit/test_review_contracts.py`

**Interfaces:**
- Produces: `semantic_review_signature(text: str) -> str`, normalizing shot IDs, numbers, punctuation, and whitespace for boilerplate comparison.
- `validate_proxy_audit()` adds deterministic finding codes without changing its signature.

- [ ] **Step 1: Write failing fabricated-audit tests**

```python
def test_proxy_audit_rejects_transcript_as_narration_meaning() -> None:
    review = _review("cue-001")
    review.narration_meaning = "evidence"
    result = validate_proxy_audit(_audit(review), _plan("cue-001"), _evidence("cue-001"))
    assert "PROXY_AUDIT_NARRATION_MEANING_INVALID" in result.finding_codes


def test_proxy_audit_rejects_repeated_visual_template() -> None:
    first = _review("cue-001", observed_visual="Hình ảnh video trong shot-001 đúng nội dung")
    second = _review("cue-002", observed_visual="Hình ảnh video trong shot-002 đúng nội dung")
    result = validate_proxy_audit(
        _audit(first, second),
        _plan("cue-001", "cue-002"),
        _evidence("cue-001", "cue-002"),
    )
    assert "PROXY_AUDIT_BOILERPLATE_INVALID" in result.finding_codes
```

- [ ] **Step 2: Run verifier tests and confirm RED**

Run: `uv run pytest tests/unit/test_review_packets.py tests/unit/test_review_contracts.py -q`
Expected: both fabricated audit cases currently pass validation.

- [ ] **Step 3: Implement deterministic fabrication guards**

For each `MATCH` review, reject when normalized `narration_meaning` equals the joined source transcript, when `observed_visual` or `note` is one of the known generic phrases, or when two cue reviews have the same normalized visual signature after removing shot identifiers and numbers. Preserve existing exact eight-frame and transcript-reference coverage checks.

- [ ] **Step 4: Run verifier tests and confirm GREEN**

Run: `uv run pytest tests/unit/test_review_packets.py tests/unit/test_review_contracts.py -q`
Expected: PASS.

- [ ] **Step 5: Commit Task 4**

```powershell
git add src/anime_review_mvp/review_packets.py src/anime_review_mvp/review_contracts.py tests/unit/test_review_packets.py tests/unit/test_review_contracts.py
git commit -m "fix: reject fabricated proxy verification"
```

### Task 5: Project six simple public stages

**Files:**
- Create: `src/anime_review_mvp/public_workflow.py`
- Modify: `src/anime_review_mvp/cli.py:315-361,491-515`
- Test: `tests/unit/test_public_workflow.py`
- Test: `tests/integration/test_autonomous_operator.py`

**Interfaces:**
- Produces: `PublicStage` enum with `PHAN_TICH`, `VIET_REVIEW`, `TAO_VOICE_VA_KHOP_CANH`, `DUNG_VIDEO`, `KIEM_TRA`, and `CHO_NGUOI_DUNG_DUYET_PROXY`.
- Produces: `public_stage(stage: Stage) -> PublicStage`.
- `next_action.json` and `operator_status.json` retain internal `stage` and add `public_stage`.

- [ ] **Step 1: Write failing stage projection tests**

```python
@pytest.mark.parametrize(
    ("internal", "expected"),
    [
        (Stage.TRICH_XUAT_BANG_CHUNG, "PHAN_TICH"),
        (Stage.CHO_ANTIGRAVITY_TINH_HUONG, "VIET_REVIEW"),
        (Stage.TAO_TTS_TINH_HUONG, "TAO_VOICE_VA_KHOP_CANH"),
        (Stage.DUNG_PROXY, "DUNG_VIDEO"),
        (Stage.KIEM_DINH_PROXY, "KIEM_TRA"),
        (Stage.CHO_NGUOI_DUNG_DUYET_PROXY, "CHO_NGUOI_DUNG_DUYET_PROXY"),
    ],
)
def test_public_stage_projection(internal: Stage, expected: str) -> None:
    assert public_stage(internal).value == expected
```

- [ ] **Step 2: Run projection tests and confirm RED**

Run: `uv run pytest tests/unit/test_public_workflow.py -q`
Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement the exhaustive mapping**

Define one mapping entry for every `Stage` member. Recovery and verifier states map to the nearest of the six public milestones; human-error stop states map to `KIEM_TRA`. Raise on an unmapped enum value so new internal stages cannot silently leak to the UI.

- [ ] **Step 4: Add public stage to JSON status artifacts**

Add `"public_stage": public_stage(state.stage).value` in initialization, `_write_next()`, and `_operator_command()` status output. Do not rename or remove the internal `stage` field, preserving integrations.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `uv run pytest tests/unit/test_public_workflow.py tests/integration/test_autonomous_operator.py tests/unit/test_cli_antigravity.py -q`
Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```powershell
git add src/anime_review_mvp/public_workflow.py src/anime_review_mvp/cli.py tests/unit/test_public_workflow.py tests/integration/test_autonomous_operator.py tests/unit/test_cli_antigravity.py
git commit -m "feat: expose a six-stage review workflow"
```

### Task 6: Offline regression and full verification

**Files:**
- Create: `tests/acceptance/test_simplified_review_pipeline.py`
- Modify: `README.md`
- Modify: `Bo_nao_Antigravity/GEMINI.md`

**Interfaces:**
- Acceptance test consumes all interfaces from Tasks 1–5 and uses only local fixtures/fake runners.
- No new production interface.

- [ ] **Step 1: Write the offline acceptance regression**

```python
def test_simplified_pipeline_reaches_proxy_gate_without_external_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = FakeServiceCalls()
    run = make_valid_fixture_run(tmp_path, voice_ms=480_000, program_ms=540_000)
    monkeypatch.setattr(cli, "synthesize_cues", calls.fake_tts)
    monkeypatch.setattr(cli, "render_review", calls.fake_render)
    drive_fixture_to_proxy_approval(run)
    assert read_state(run).stage is Stage.CHO_NGUOI_DUNG_DUYET_PROXY
    assert calls.network_calls == 0
    assert json.loads((run / "operator_status.json").read_text())["public_stage"] == (
        "CHO_NGUOI_DUNG_DUYET_PROXY"
    )
```

- [ ] **Step 2: Run acceptance test and confirm behavior**

Run: `uv run pytest tests/acceptance/test_simplified_review_pipeline.py -q`
Expected: PASS without network access, real TTS, or real FFmpeg rendering.

- [ ] **Step 3: Update operator documentation**

Document the six public stages, the `RUN_CODE_IDENTITY_MISMATCH` recovery message, the per-cue evidence sizing rule, and the fact that measured machine failures cannot be overridden by semantic verification. Remove any instruction suggesting copying old drafts or manually writing PASS files.

- [ ] **Step 4: Run the complete test suite**

Run: `uv run pytest -q`
Expected: all tests PASS.

- [ ] **Step 5: Run static repository checks**

Run: `git diff --check`
Expected: no output and exit code 0.

Run: `rg -n "verdict=\"MATCH\"|verdict=\"CLEAN\"" . -g '*.py' -g '!tests/**'`
Expected: no production helper that fabricates verifier outcomes.

- [ ] **Step 6: Commit Task 6**

```powershell
git add tests/acceptance/test_simplified_review_pipeline.py README.md Bo_nao_Antigravity/GEMINI.md
git commit -m "test: prove simplified review pipeline offline"
```

- [ ] **Step 7: Inspect final history and workspace**

Run: `git status --short`
Expected: empty output.

Run: `git log --oneline -7`
Expected: the design commit, plan commit, and six implementation commits are present.
