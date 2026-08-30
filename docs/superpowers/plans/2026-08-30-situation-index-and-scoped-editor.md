# Situation Index and Scoped Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require an Antigravity-authored, engine-validated episode situation index and guarantee that every subsequent editorial task contains data from exactly one indexed situation.

**Architecture:** Add a structure-task contract and strict situation-index model before the existing per-situation editor loop. A deterministic scoper materializes transcript, shot, and frame subsets, hashes them, and the workflow derives progression from the accepted index rather than arbitrary IDs.

**Tech Stack:** Python 3.12 dataclasses, JSON artifacts, pytest, existing atomic JSON/provenance/workflow modules.

**Spec:** `docs/superpowers/specs/2026-08-30-situation-index-and-scoped-editor-design.md`

## Global Constraints

- Antigravity is the sole content editor; engine code must not infer story meaning.
- No task may install a dependency or plugin automatically.
- Per-situation tasks must not contain or reference full-episode evidence files.
- Preserve all existing user changes and runtime media.
- Gemini/Chrome remains optional and cannot advance the default workflow.
- Use TDD and commit each independently testable task.

---

### Task 1: Define and validate the situation index

**Files:**
- Create: `src/anime_review_mvp/situation_index.py`
- Create: `tests/unit/test_situation_index.py`

**Interfaces:**
- Produces `SituationIndexEntry`, `SituationIndexDocument`,
  `load_situation_index(path, source, transcript, shots, frames)`, and
  `next_editable_situation(index, locked_ids)`.

- [ ] Write failing tests for unique ordered IDs, valid ranges, no overlap, existing
  transcript/shot/frame refs, exclusion reasons, source hash and at least one editable
  entry.
- [ ] Run `pytest tests/unit/test_situation_index.py -v` and verify failure because
  the module does not exist.
- [ ] Implement strict dataclasses and validation without story inference.
- [ ] Run the focused test and verify PASS.
- [ ] Commit `feat: validate Antigravity situation index`.

### Task 2: Add the episode-structure task contract

**Files:**
- Create: `src/anime_review_mvp/structure_packets.py`
- Create: `tests/unit/test_structure_packets.py`
- Modify: `src/anime_review_mvp/editor_provenance.py`
- Modify: `tests/unit/test_editor_provenance.py`

**Interfaces:**
- Produces `StructureEditorPacket`, `create_structure_task(...)`, and
  `render_structure_editor_prompt(packet)`.
- Structure task allows only `situation_index_draft.json` in its staging directory.

- [ ] Write failing contract tests proving the task cannot emit narration/EDL/TTS and
  the prompt requires semantic boundaries plus evidence refs.
- [ ] Run focused tests and verify failure.
- [ ] Implement the packet and generalize provenance to distinguish `STRUCTURE` from
  `SITUATION` tasks with exact allowed outputs.
- [ ] Run focused tests and verify PASS.
- [ ] Commit `feat: add Antigravity structure task`.

### Task 3: Materialize fail-closed scoped evidence

**Files:**
- Create: `src/anime_review_mvp/situation_scope.py`
- Create: `tests/unit/test_situation_scope.py`
- Modify: `src/anime_review_mvp/situation_packets.py`
- Modify: `tests/unit/test_situation_packets.py`

**Interfaces:**
- Produces `SituationScope`, `materialize_situation_scope(...) -> SituationScope`, and
  `validate_submission_scope(...)`.
- `build_situation_editor_packet` consumes scoped paths and the accepted index hash.

- [ ] Write failing tests with transcript segments, shots and frames before/inside/
  after a range; assert outputs contain only inside/intersecting evidence and never
  reference the full manifest.
- [ ] Add failing tests for empty scope, stale index hash and output refs outside range.
- [ ] Run focused tests and verify failure.
- [ ] Implement atomic scoped JSON generation, shot clamping and scope hashes.
- [ ] Change the situation packet to serialize scoped paths/data only.
- [ ] Run focused tests and verify PASS.
- [ ] Commit `feat: scope every editorial task to one situation`.

### Task 4: Insert structure stages and index-driven progression

**Files:**
- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `tests/unit/test_workflow.py`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `tests/unit/test_cli_situations.py`

**Interfaces:**
- Adds stages `CHO_ANTIGRAVITY_CHIA_TINH_HUONG` and
  `KIEM_DINH_CHI_MUC_TINH_HUONG`.
- Adds CLI commands `structure-task` and `accept-situation-index`.
- `editor-task` requires accepted `situation_index.json` and chooses the next unlocked
  non-excluded entry.

- [ ] Write failing workflow tests proving `prepare` stops at structure-task, editor
  task cannot start early, and progression is derived from index order.
- [ ] Write failing CLI tests proving `prepare` no longer invents `situation-001` and
  `accept-situation-index` rejects invalid/stale submissions.
- [ ] Run focused tests and verify failure.
- [ ] Implement stage/state compatibility, CLI orchestration and exact next actions.
- [ ] Validate Antigravity outputs against scope before accepting or merging them.
- [ ] Run focused tests and verify PASS.
- [ ] Commit `feat: drive editorial workflow from situation index`.

### Task 5: Migrate the active run and add end-to-end regression

**Files:**
- Modify: `tests/integration/test_situation_pipeline.py`
- Modify: `docs/antigravity-editorial-runbook.md`
- Runtime only: `Tam_dang_xu_ly/c640e72b78d3404e9719898998196478/`

**Interfaces:**
- Adds migration behavior for pre-index v2 runs without deleting prior tasks.

- [ ] Write a failing integration test for structure submission → accepted index →
  scoped situation task → accepted drafts → next indexed situation.
- [ ] Add regression proving whole-episode evidence is absent from the situation task.
- [ ] Run the integration test and verify failure.
- [ ] Implement migration and update the operator runbook.
- [ ] Run migration on the active Black Torch run, verify old task is preserved as
  superseded, and verify the new next action requests structure only.
- [ ] Run integration tests and verify PASS.
- [ ] Commit `test: prove indexed scoped editorial handoff`.

### Task 6: Integrate with dirty main and verify the deployed project

**Files:**
- Preserve and reconcile existing main changes in `pyproject.toml`, `uv.lock`, CLI,
  Gemini modules and their tests.
- No generated media is added to Git.

**Interfaces:**
- The deployed `feature/anime-review-mvp` branch contains both the local indexed
  pipeline and optional Gemini/browser maintenance code.

- [ ] Record hashes/diffs of all dirty main files before integration.
- [ ] Create a recoverable patch of dirty tracked changes without deleting or stashing
  untracked media.
- [ ] Fast-forward the main branch to the completed worktree branch.
- [ ] Reapply only the preserved user changes, resolve overlaps per hunk and verify the
  default state path still contains no Gemini gate.
- [ ] Run `ruff check src tests run_episode.py` and `pytest -q`.
- [ ] Run CLI smoke tests from the main checkout and inspect the active run's
  `next_action.json` plus scoped task JSON.
- [ ] Confirm no missing dependency; if one is missing, stop and tell the user exactly
  what to install.

## Final Verification Checklist

- [ ] `prepare` creates a structure task, not `situation-001`.
- [ ] Invalid or stale situation indexes fail closed.
- [ ] Every editor packet contains one scope and no full-episode evidence.
- [ ] Every accepted output is revalidated against its scope.
- [ ] The next situation comes only from accepted index order.
- [ ] The active run points to a structure task and preserves the prior revision.
- [ ] Main checkout passes lint and the complete test suite.
- [ ] Main dirty/untracked user files are preserved.
- [ ] No tool, plugin or dependency was installed automatically.
