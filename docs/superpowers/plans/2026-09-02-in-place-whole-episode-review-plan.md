# In-Place Whole-Episode Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the canonical per-situation Antigravity loop with one resumable whole-episode editorial task while preserving the working evidence extraction, TTS cache, semantic timeline, rendering, and proxy safeguards.

**Architecture:** Extend the existing situation-v2 code path in place. The accepted situation index remains the source-boundary contract; one `EPISODE_REVIEW` task produces a complete situation document and narration plan, which are globally validated and atomically accepted before one cache-aware TTS/timeline/render pass. Legacy task kinds and stages remain readable for archives but are never emitted for a new or migrated run.

**Tech Stack:** Python 3.12, Pydantic/dataclasses already used by the project, Typer CLI, pytest, FFmpeg/ffprobe, the existing JSON provenance and content-addressed TTS cache.

**Spec:** `docs/superpowers/specs/2026-09-02-in-place-whole-episode-review-design.md`

## Global Constraints

- Do not create a second pipeline, command family, run directory, or alternate set of canonical artifacts.
- Keep `situation_index.json`, `Su_that/situations.json`, `Kich_ban/narration_plan.json`, `adaptive_edl.json`, `semantic_timeline.json`, `cue_tts_manifest.json`, and `proxy/review_proxy.mp4` as the canonical artifact names.
- Preserve source observations, frames, transcript/SRT, shots, source identity, policy identity, and valid content-addressed cue audio.
- New canonical runs must not require `locked_situation_ids` and must not emit per-situation verifier stages.
- Exact accepted voice duration remains `420000..720000` ms. Do not lower the seven-minute minimum.
- Every behavior change starts with a failing test. Run the focused test after each code change and commit each task independently.
- Keep the legacy `SITUATION`, `SITUATION_AUDIT`, and `PROXY_AUDIT` readers only where old revision archives require them.

---

## Task 1: Add the whole-episode provenance contract

**Files:**

- Modify: `src/anime_review_mvp/editor_provenance.py`
- Modify: `tests/unit/test_editor_provenance.py`

- [ ] Add a failing test proving `create_editor_task(..., task_kind="EPISODE_REVIEW", situation_id="__episode__")` is accepted and records exactly `situations_draft.json` and `narration_draft.json` as its output contract.
- [ ] Add a failing test proving the same task ID, input hash, source hash, policy hash, and byte-identical drafts can be accepted idempotently after reconnect, while a changed hash is rejected as stale.
- [ ] Extend `_EDITOR_TASK_KINDS` with `EPISODE_REVIEW` and add an explicit task-output mapping:

```python
_EDITOR_TASK_OUTPUTS = {
    "EPISODE_REVIEW": ("situations_draft.json", "narration_draft.json"),
}
```

- [ ] Make task creation serialize the expected output names. Make acceptance verify both files exist, hash both files, and record both hashes in the accepted ledger.
- [ ] Make byte-identical re-acceptance return the existing accepted record instead of appending a duplicate or raising a stale-submission error.
- [ ] Run `uv run pytest tests/unit/test_editor_provenance.py -q`.
- [ ] Commit with `git commit -am "feat: add whole-episode editor provenance"`.

## Task 2: Give Antigravity one unambiguous whole-episode packet

**Files:**

- Modify: `src/anime_review_mvp/situation_packets.py`
- Modify: `tests/unit/test_situation_packets.py`
- Modify: `tests/unit/test_antigravity_contract.py`

- [ ] Add failing tests for an `EpisodeReviewPacket` containing the accepted index path, complete transcript/SRT references, shot manifest, frame manifest, style profile, duration policy, source/policy hashes, current revision, and optional previous full drafts plus measured-duration repair context.
- [ ] Add failing prompt-contract assertions for all of the following phrases/meanings: one task for the complete episode; inspect referenced frames directly; use transcript, SRT, shots, and frames together; preserve chronological order; exclude opening/ending/credits/preview/bumper/logo material; target 7–12 minutes; write exactly two draft files; submit through the acceptance command; do not create scripts to generate JSON; do not inspect validator implementation; do not emit `GOAL_COMPLETE`.
- [ ] Implement:

```python
@dataclass(frozen=True)
class EpisodeReviewPacket:
    task_kind: Literal["EPISODE_REVIEW"]
    situation_id: Literal["__episode__"]
    revision: int
    situation_index_path: Path
    transcript_paths: tuple[Path, ...]
    shot_manifest_path: Path
    frame_manifest_path: Path
    style_profile_path: Path
    policy_path: Path
    output_dir: Path
    previous_situations_path: Path | None = None
    previous_narration_path: Path | None = None
    measured_voice_ms: int | None = None
    repair_code: str | None = None
```

- [ ] Implement `build_episode_review_packet(...)` and `render_episode_review_prompt(packet)` in the existing packet module; do not add a separate prompt subsystem.
- [ ] Ensure the prompt prints absolute Windows-safe paths and an exact acceptance command generated by the existing CLI contract.
- [ ] Retain the old per-situation prompt only for archived-task inspection; remove it from canonical operator selection in Task 4.
- [ ] Run `uv run pytest tests/unit/test_situation_packets.py tests/unit/test_antigravity_contract.py -q`.
- [ ] Commit with `git commit -am "feat: instruct one whole-episode editorial task"`.

## Task 3: Validate complete episode coverage before TTS

**Files:**

- Modify: `src/anime_review_mvp/situation_scope.py`
- Modify: `src/anime_review_mvp/situation_validation.py`
- Modify: `src/anime_review_mvp/editorial_budget.py`
- Modify: `tests/unit/test_situation_validation.py`
- Modify: `tests/unit/test_editorial_budget.py`

- [ ] Add table-driven failing tests for missing, duplicate, reordered, unknown, and excluded situation IDs; ranges outside indexed boundaries; cues assigned to the wrong unit/situation; unknown shot/frame references; transcript/SRT references that do not overlap the kept range; and narration that fails the existing claim/evidence grounding check.
- [ ] Implement `validate_episode_submission_scope(index, situations, narration_plan, evidence_catalog)` so the editable index IDs exactly equal situation IDs and narration unit situation IDs in source order. Reuse existing model and grounding validators rather than duplicating them.
- [ ] Add failing budget tests with a deterministic 150 spoken-words/minute planning estimate. At `420000..720000` ms, accept `1050..1800` substantive words and reject outside values with `EPISODE_SCRIPT_BUDGET_TOO_SHORT` or `EPISODE_SCRIPT_BUDGET_TOO_LONG`. Keep the existing per-cue readability ceiling.
- [ ] Implement:

```python
@dataclass(frozen=True)
class EpisodeWordBudget:
    total_words: int
    minimum_words: int = 1050
    maximum_words: int = 1800

def validate_episode_word_budget(plan: NarrationPlan) -> EpisodeWordBudget:
    return EpisodeWordBudget(total_words=count_spoken_words(plan))
```

- [ ] Count Unicode word tokens from spoken cue text after trimming punctuation-only tokens; do not manipulate punctuation to conceal pauses or inflate the count.
- [ ] Run `uv run pytest tests/unit/test_situation_validation.py tests/unit/test_editorial_budget.py -q`.
- [ ] Commit with `git commit -am "feat: validate whole-episode editorial coverage"`.

## Task 4: Simplify the workflow and operator to one editorial job

**Files:**

- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `src/anime_review_mvp/operator.py`
- Modify: `tests/unit/test_workflow.py`
- Modify: `tests/integration/test_autonomous_operator.py`

- [ ] Add a failing state-sequence test for `CHUAN_BI -> TRICH_XUAT_BANG_CHUNG -> CHO_ANTIGRAVITY_CHIA_TINH_HUONG -> KIEM_DINH_CHI_MUC_TINH_HUONG -> CHO_ANTIGRAVITY_TINH_HUONG -> KIEM_DINH_TINH_HUONG -> TAO_TTS_TINH_HUONG -> LAP_TIMELINE_TINH_HUONG -> KIEM_DINH_MACH_TRUYEN_TOAN_TAP -> DUNG_PROXY -> KIEM_DINH_PROXY -> CHO_NGUOI_DUNG_DUYET_PROXY`.
- [ ] Add a failing operator test proving `CHO_ANTIGRAVITY_TINH_HUONG` returns `PREPARE_EPISODE_REVIEW_JOB`, never selects a next unlocked situation, and reuses the same `editor_task_id` when one is active.
- [ ] Add a failing test proving global acceptance advances once without modifying `locked_situation_ids` and that the canonical route never emits situation-producer, situation-audit, or per-situation verifier actions.
- [ ] Implement `begin_episode_review_task`, `accept_episode_review_revision`, and `route_episode_review_repair` as focused workflow transitions using `situation_id="__episode__"`. A repair increments the episode revision, clears the active task only after recording its failure, and keeps the complete accepted drafts as repair input.
- [ ] Change `plan_operator_step` to base canonical decisions on stage and active episode task identity, not on `editable_ids - locked_situation_ids`.
- [ ] Preserve legacy transition readers/functions for archives, but mark them non-canonical in docstrings and stop calling them from the operator.
- [ ] Run `uv run pytest tests/unit/test_workflow.py tests/integration/test_autonomous_operator.py -q`.
- [ ] Commit with `git commit -am "refactor: use one episode editorial workflow"`.

## Task 5: Accept and publish both editorial drafts as one revision

**Files:**

- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/jsonio.py`
- Modify: `tests/unit/test_cli_situations.py`
- Modify: `tests/unit/test_jsonio.py`

- [ ] Add a failing CLI test proving `editor-task` at `CHO_ANTIGRAVITY_TINH_HUONG` creates one `EPISODE_REVIEW` task and prompt with no per-situation scope.
- [ ] Add failing acceptance tests proving one invalid draft publishes neither canonical file, two valid drafts publish together, and a crash/reconnect after staging can safely finish the same accepted revision without duplicate ledger entries.
- [ ] Add `atomic_publish_json_pair(staged_a, target_a, staged_b, target_b, manifest_path, hashes)` using temp files and `os.replace`. Write the hash manifest last; consumers verify the manifest and both hashes before advancing or loading the pair.
- [ ] Branch `_accept_antigravity_command` by task kind. For `EPISODE_REVIEW`, load both drafts, run model/scope/grounding/word-budget validation, copy both into one accepted revision directory, publish the canonical pair, write the manifest, and call `accept_episode_review_revision` only after all writes succeed.
- [ ] Make repeated acceptance of the same task and hashes finish any incomplete publication and return success without creating a second revision.
- [ ] Leave the old `SITUATION` acceptance branch only for replaying archived tasks; canonical operator commands must never create it.
- [ ] Run `uv run pytest tests/unit/test_cli_situations.py tests/unit/test_jsonio.py -q`.
- [ ] Commit with `git commit -am "feat: publish complete episode drafts atomically"`.

## Task 6: Enforce exact duration immediately after one cache-aware TTS pass

**Files:**

- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/editorial_budget.py`
- Modify: `tests/unit/test_situation_tts.py`
- Modify: `tests/unit/test_cli_situations.py`

- [ ] Add a failing test proving TTS runs once for the complete accepted plan and unchanged cue text reuses existing content-addressed WAV files.
- [ ] Add failing tests proving measured totals below `420000` ms and above `720000` ms return the entire episode to a new `EPISODE_REVIEW` revision with `EPISODE_VOICE_BUDGET_TOO_SHORT` or `EPISODE_VOICE_BUDGET_TOO_LONG`; timeline construction must not begin.
- [ ] Move the existing exact `validate_episode_voice_budget` gate from the timeline command to the end of the TTS command. Keep a defensive recheck at timeline entry without changing state on success.
- [ ] Store measured duration and repair code in the next episode packet, plus paths to the last complete accepted drafts. Do not route the error to the last situation and do not clear valid cached cue audio.
- [ ] Add a reconnect test proving an interrupted TTS pass reads the manifest/cache, synthesizes only missing cue files, recomputes the full total, and never pairs voice from one revision with visuals from another.
- [ ] Run `uv run pytest tests/unit/test_situation_tts.py tests/unit/test_cli_situations.py -q`.
- [ ] Commit with `git commit -am "fix: repair voice duration across the whole episode"`.

## Task 7: Remove verifier loops from timeline and proxy progression

**Files:**

- Modify: `src/anime_review_mvp/cli.py`
- Modify: `tests/unit/test_cli_situations.py`
- Add: `tests/acceptance/test_simplified_review_pipeline.py`

- [ ] Add a failing acceptance test using fixture media/artifacts to prove the canonical happy path creates exactly one editorial task, one global acceptance, one TTS manifest, one semantic timeline, one proxy, and stops at `CHO_NGUOI_DUNG_DUYET_PROXY`.
- [ ] Add assertions that no `SITUATION_AUDIT`/per-cue verifier task is created, all narration cues map to their own accepted visual anchors, playback rates stay within `0.80..1.30`, and no source event is reordered.
- [ ] Simplify `_audit_situation_v2` into one global content validation before TTS; route failures to `route_episode_review_repair`. Remove verifier-task creation from `_operator_engine_step`.
- [ ] Remove the lock-completeness prerequisite from `_timeline_command`. Verify the accepted pair manifest, exact TTS duration, complete cue coverage, and current revision identity instead.
- [ ] Preserve the existing bumper/logo, excluded-segment, loudness, artifact-identity, cue-coverage, and A/V timing proxy audits.
- [ ] Add a completion assertion: `GOAL_COMPLETE` is impossible unless `proxy/review_proxy.mp4` exists outside `revisions` and state equals `CHO_NGUOI_DUNG_DUYET_PROXY`.
- [ ] Run `uv run pytest tests/unit/test_cli_situations.py tests/acceptance/test_simplified_review_pipeline.py -q`.
- [ ] Commit with `git commit -am "refactor: render one globally validated episode"`.

## Task 8: Migrate the current partial run without preserving confusing derivatives

**Files:**

- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `tests/unit/test_cli_situations.py`

- [ ] Build a failing migration fixture matching the current run: `CAN_CON_NGUOI_XU_LY`, 22 locked situation IDs, a partial narration/TTS chain, stale audit/status files, and an archived proxy.
- [ ] Implement an explicit `migrate-whole-episode-review` CLI operation used by the operator when a run still carries canonical per-situation locks/history.
- [ ] Resolve and verify the run path before moving anything. Archive only editorial drafts/accepted revisions, TTS derivatives/manifests, timelines/EDLs, audits, status files, and proxy attempts beneath `revisions/whole-episode-review-revision-N`.
- [ ] Preserve source video references, source fingerprint, transcript/SRT, shots, frames, source cache, policy/config, and a `situation_index.json` that still validates against current source/policy identity.
- [ ] Reset the canonical state to `CHO_ANTIGRAVITY_TINH_HUONG`, clear locks and per-situation repair history, set current situation to `__episode__`, clear stale task/status IDs, and create one fresh `EPISODE_REVIEW` task. If index identity/validation fails, reset to `CHO_ANTIGRAVITY_CHIA_TINH_HUONG` instead.
- [ ] Make migration idempotent: rerunning it must not create another archive or task when the run already has the whole-episode migration marker and an active valid task.
- [ ] Run `uv run pytest tests/unit/test_cli_situations.py -q`.
- [ ] Commit with `git commit -am "feat: migrate partial runs to whole-episode review"`.

## Task 9: Align operator instructions and documentation

**Files:**

- Modify: `README.md`
- Modify: `Bo_nao_Antigravity/GEMINI.md`
- Modify: `docs/antigravity-editorial-runbook.md`
- Modify: `src/anime_review_mvp/cli.py` (`_tagged_operator_prompt`)
- Modify: `tests/unit/test_antigravity_contract.py`

- [ ] Add failing contract tests proving no canonical instruction asks Antigravity to process, lock, TTS, timeline, or verify one situation at a time.
- [ ] Rewrite the canonical instructions as the short operational loop: read `next_action.json` and the one episode packet; inspect transcript/SRT/frames/shots; write the two complete drafts; run accept; run operator; resume the same task after reconnect; stop only for a concrete missing tool or at user proxy approval.
- [ ] State plainly that the operator owns validation/TTS/timeline/render, Antigravity owns editorial judgment, and the user owns final proxy approval.
- [ ] Remove obsolete examples that advertise 42/per-situation states or imply `GOAL_COMPLETE` can be emitted after structure/editorial work.
- [ ] Document proxy resolution as intentionally lower quality than final source while retaining full semantic/timing checks.
- [ ] Run `uv run pytest tests/unit/test_antigravity_contract.py -q`.
- [ ] Commit with `git commit -am "docs: simplify Antigravity whole-episode operation"`.

## Task 10: Full verification and controlled current-run migration

**Files:**

- Verify: all modified source, tests, and docs
- Runtime target: `Tam_dang_xu_ly/8955a477cd66496990676b670f89af6c`

- [ ] Run `uv run pytest -q` and record the exact passed/failed/skipped totals.
- [ ] Run `uv run ruff check src tests` and `uv run ruff format --check src tests` as configured in `pyproject.toml`.
- [ ] Run a read-only preflight against the current runtime and print the resolved episode path, current source/policy hashes, preserved evidence paths, files to archive, and target revision directory.
- [ ] Execute the migration only after the preflight targets are verified to remain inside the named runtime. Do not delete source evidence; the archive must be recoverable beneath `revisions`.
- [ ] Run `uv run --project "D:\FINAL REVIEW ANIME\.worktrees\antigravity-tagged-autonomous-operator" python "D:\FINAL REVIEW ANIME\.worktrees\antigravity-tagged-autonomous-operator\run_episode.py" operator --run "D:\FINAL REVIEW ANIME\.worktrees\antigravity-tagged-autonomous-operator\Tam_dang_xu_ly\8955a477cd66496990676b670f89af6c"` once and verify `next_action.json` requests exactly one `EPISODE_REVIEW` task or reports the already active matching task.
- [ ] Verify `run_state.json` is atomically readable, `locked_situation_ids` is empty, current situation is `__episode__`, no new proxy exists prematurely, and the Antigravity prompt names exactly the two draft outputs.
- [ ] Run `git status --short` and confirm only intentional tracked changes plus the pre-existing untracked `Kho_Anime/` runtime remain.
- [ ] Use `superpowers:verification-before-completion`, then commit any verification-only fixes with a scoped message. Do not claim that a new 7–12 minute video exists until Antigravity submits the full drafts and the operator actually renders it.

## Plan Self-Review

- Every success criterion in the approved spec is covered by at least one test above.
- No task introduces a parallel pipeline or replaces working FFmpeg/TTS/evidence components.
- The duration bounds, playback-rate bounds, task kind, situation ID, draft names, state sequence, and current runtime path are explicit.
- Crash recovery is covered at task acceptance, TTS, and migration boundaries.
- Destructive scope is limited to moving named derivative files into a verified recoverable revision directory.
- There are no placeholder functions, unspecified schemas, or deferred implementation decisions in this plan.
