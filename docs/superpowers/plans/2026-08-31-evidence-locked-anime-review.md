# Evidence-Locked Anime Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce an autonomous Antigravity rebuild that produces a 7–12 minute, continuously narrated, evidence-locked anime review without engine-side editorial compaction.

**Architecture:** Add run-level reference and episode-budget contracts, make every cue own an exact source interval, build the semantic timeline without trimming accepted footage, and verify actual source/proxy frames per cue. Production render and audit gates enforce duration, narration continuity, excluded-content boundaries, and measured audio consistency.

**Tech Stack:** Python 3.12, dataclasses, JSON artifacts, FFmpeg/FFprobe, pytest, Ruff

**Spec:** `docs/superpowers/specs/2026-08-31-evidence-locked-anime-review.md`

## Global Constraints

- Antigravity is the only content editor; Codex never writes episode narration or selects episode footage.
- Production duration is 420,000–720,000 ms.
- Normal inter-cue pause is 80–900 ms and the hard maximum is 1,200 ms.
- Every cue has exact source evidence and four source plus four proxy verification frames.
- No accepted editorial interval may be compacted or remapped after acceptance.
- Missing tools are reported and never installed silently.

---

### Task 1: Reference and episode-budget contracts

**Files:**
- Create: `src/anime_review_mvp/editorial_budget.py`
- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `src/anime_review_mvp/antigravity.py`
- Modify: `src/anime_review_mvp/gemini_packets.py`
- Test: `tests/unit/test_editorial_budget.py`
- Test: `tests/unit/test_operator.py`

**Interfaces:**
- Produces: `ReferenceStyleProfile`, `SituationBudget`, `EpisodeEditorialBudget`, and validation that total predicted output fits 420,000–720,000 ms.
- Consumes: source/reference paths and SHA-256 values already exposed by run configuration.

- [ ] Write failing behavioral tests for a missing reference profile, invalid reference hash, under-budget plan, over-budget plan, and valid weighted plan.
- [ ] Run the focused tests and confirm they fail because the contracts and workflow gates do not exist.
- [ ] Implement the dataclasses, JSON validation, task packet fields, and operator routing for reference analysis then episode budgeting.
- [ ] Run the focused tests and confirm they pass.
- [ ] Commit the reference and budget contract changes.

### Task 2: Cue-owned evidence intervals and non-compacting timeline

**Files:**
- Modify: `src/anime_review_mvp/situations.py`
- Modify: `src/anime_review_mvp/situation_validation.py`
- Modify: `src/anime_review_mvp/semantic_timeline.py`
- Modify: `src/anime_review_mvp/situation_packets.py`
- Test: `tests/unit/test_situations.py`
- Test: `tests/unit/test_situation_validation.py`
- Test: `tests/unit/test_semantic_timeline.py`

**Interfaces:**
- Produces: cue `source_start_ms`/`source_end_ms`; timeline segments that exactly preserve cue-owned accepted evidence.
- Consumes: `EpisodeEditorialBudget` from Task 1 and existing TTS cue durations.

- [ ] Write failing tests proving a cue cannot borrow an entire situation interval, mix semantic events, omit its anchor, or rely on engine compaction.
- [ ] Run focused tests and verify the expected contract/timeline failures.
- [ ] Add cue interval fields and validators; replace `_compact_unit` with sequential cue-locked layout that routes insufficient footage back to Antigravity.
- [ ] Run focused tests and confirm exact source/program mappings and 1,200 ms continuity gates pass.
- [ ] Commit cue evidence and timeline changes.

### Task 3: Hard production render and continuity gates

**Files:**
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/render.py`
- Modify: `src/anime_review_mvp/local_audit.py`
- Modify: `src/anime_review_mvp/cue_audio.py`
- Test: `tests/unit/test_render.py`
- Test: `tests/unit/test_local_audit.py`
- Test: `tests/unit/test_cli_situations.py`
- Test: `tests/unit/test_cue_audio.py`

**Interfaces:**
- Produces: proxy/final rejection outside 420,000–720,000 ms; rejection for cue gaps above 1,200 ms; measured loudness and per-cue level-spread findings.
- Consumes: semantic timeline and normalized cue audio.

- [ ] Write failing tests showing the v2 proxy and final paths currently bypass duration bounds and permit excessive narration gaps.
- [ ] Run focused tests and confirm the bypass is reproduced.
- [ ] Remove `duration_bounds_ms=None`, tighten continuity findings, and expose real loudness/level-spread measurements to audit.
- [ ] Run focused tests and confirm all production gates pass.
- [ ] Commit render and continuity gates.

### Task 4: Exact per-cue proxy evidence and verifier contract

**Files:**
- Modify: `src/anime_review_mvp/proxy_evidence.py`
- Modify: `src/anime_review_mvp/review_packets.py`
- Modify: `src/anime_review_mvp/review_contracts.py`
- Test: `tests/unit/test_proxy_evidence.py`
- Test: `tests/unit/test_review_packets.py`
- Test: `tests/unit/test_review_contracts.py`

**Interfaces:**
- Produces: `CueProxyEvidence` using exact cue source/program intervals and START/ANCHOR/MIDDLE/END frames.
- Consumes: cue-owned intervals and semantic timeline from Task 2.

- [ ] Write failing tests where two cues in one situation show different events and the old situation-wide evidence would incorrectly permit MATCH.
- [ ] Run focused tests and confirm the verifier cannot distinguish the cues.
- [ ] Generate cue-exact source/program bundles, include SRT/transcript references, and require verifier coverage/verdict for every evidence position.
- [ ] Run focused tests and confirm mismatched cue imagery is rejected.
- [ ] Commit proxy evidence changes.

### Task 5: Fresh-run migration and autonomous Antigravity instructions

**Files:**
- Modify: `Bo_nao_Antigravity/GEMINI.md`
- Modify: `src/anime_review_mvp/cli.py`
- Modify: `src/anime_review_mvp/workflow.py`
- Modify: `src/anime_review_mvp/gemini_packets.py`
- Test: `tests/unit/test_operator.py`
- Test: `tests/unit/test_cli_situations.py`
- Test: `tests/unit/test_gemini_packets.py`

**Interfaces:**
- Produces: migration that invalidates stale editorial artifacts, preserves source analysis, records the reference path/hash, and schedules a full autonomous rebuild.
- Consumes: all new contracts and gates from Tasks 1–4.

- [ ] Write failing integration tests for stale-run invalidation, one-prompt autonomous looping, exact missing-tool reporting, and stopping only at `CHO_NGUOI_DUNG_DUYET_PROXY`.
- [ ] Run focused tests and confirm current workflow reuses invalid editorial state.
- [ ] Implement migration, job prompts, reference-view requirement, budget task, and operator loop behavior.
- [ ] Run focused integration tests and confirm Antigravity—not Codex—owns all editorial tasks.
- [ ] Commit autonomous rebuild changes.

### Task 6: Full regression verification

**Files:**
- Modify only files required by failures discovered during verification.

**Interfaces:**
- Consumes: complete implementation from Tasks 1–5.
- Produces: verified branch ready for the user to launch Antigravity once.

- [ ] Run `uv run ruff check src tests` and fix any reported issue through a failing regression test when behavior changes.
- [ ] Run `uv run pytest -q` and resolve every failure without weakening approved gates.
- [ ] Inspect `git diff --check`, `git status --short`, and the final diff; preserve untracked user-owned `Kho_Anime/`.
- [ ] Re-read the design spec and map every requirement to a passing test or explicit human-facing instruction.
- [ ] Commit final regression fixes and report the exact test/lint counts.
