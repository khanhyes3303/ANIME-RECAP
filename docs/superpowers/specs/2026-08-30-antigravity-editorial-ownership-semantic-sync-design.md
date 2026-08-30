# Antigravity Editorial Ownership and Semantic Sync Design

**Date:** 2026-08-30  
**Status:** Proposed for user review  
**Scope:** The situation-first local anime-review workflow and the BLACK TORCH episode-1 rerun

## Goal

Make Antigravity the only editorial author for episode artifacts while Codex owns only
the engine, schemas, validators, tests, and operator repair. Prevent narration from
describing a person, action, reveal, or result before the corresponding image appears.
Require a story that a viewer with no prior knowledge of the anime can follow. Never
publish a final video until the user explicitly approves a proxy.

## Confirmed failures

The current BLACK TORCH render is technically synchronized but semantically early. Its
video stream ends at 426.509 seconds and its audio stream at 426.504 seconds, so the
measured stream drift is only 5 milliseconds. That metric does not describe editorial
synchronization.

At program time 28.728 seconds, unit 004 starts playing narration that immediately says
Jiro has returned to the family dojo and that his grandfather is waiting. The visual at
28.278 seconds still shows Jiro and the crow. The grandfather does not appear until the
visual change sampled at 35.786 seconds. The narration therefore reveals the next image
roughly five to seven seconds early even though the two streams have nearly identical
total duration.

The script also begins without explaining who Jiro is, introduces names and terms before
giving the viewer a usable role, and repeats mechanical transitions such as “tiếp đó”,
“mà oái oăm”, and “chưa kịp thở”. Existing local and engine audits pass because they
check evidence coverage, clip gaps, playback rate, stream counts, and total duration;
they do not check sentence-to-image timing or newcomer comprehension.

## Non-goals

- Codex will not write or rewrite episode narration, choose story facts, or select final
  evidence ranges.
- Gemini Web will not return to the default workflow.
- A global five-second audio shift will not be used. Different facts occur at different
  offsets, so a global shift would merely move the error elsewhere.
- The engine will not attempt to infer story quality from word-count heuristics alone.
- Existing source video, transcripts, frames, and previous final renders will not be
  destroyed.

## Roles and authority

### Antigravity: editorial owner

Antigravity reads the transcript/SRT, frames, shot boundaries, prior-episode context,
and current situation packet. It alone authors:

- the situation facts and their main/supporting classification;
- the narration and bridges;
- the evidence ranges and visual anchors;
- character and term introductions;
- the decision to keep, shorten, or omit an action;
- repairs requested by semantic validation or user proxy review.

Antigravity processes one situation at a time. It cannot advance to the next situation
until the current situation has accepted editorial artifacts, synthesized TTS, a built
cue timeline, and a passing situation-level semantic review.

### Codex: engine and validator owner

Codex may change source code, schemas, validators, tests, operator prompts, diagnostics,
and rendering behavior. Codex may investigate a failed artifact and report exact finding
codes. Codex must not repair an episode by editing its narration, story facts, evidence
ranges, or cue anchors. When editorial content fails, the engine routes a structured
repair packet back to Antigravity.

### Engine: deterministic authority

The engine owns stage transitions, immutable provenance records, hashing, TTS assembly,
EDL calculation, audit reports, and publication. Neither Antigravity nor Codex may write
`run_state.json` or declare a technical PASS directly.

### User: publication authority

The user reviews the proxy. Only an explicit proxy approval may unlock final rendering
and publication. A local audit PASS is necessary but never sufficient for final output.

## Artifact model

### Editor task and provenance

For each situation the engine creates an `editor_task.json` containing:

- `task_id`, `run_id`, and `situation_id`;
- hashes of transcript, frames, shots, policy, and prior accepted context;
- the expected stage and allowed output filenames;
- a monotonically increasing editorial revision.

Antigravity submits `situation_draft.json` and `narration_draft.json` through a dedicated
`accept-antigravity` command. The engine validates the current task ID and input hashes,
then writes an append-only `editor_ledger.jsonl` record with actor `ANTIGRAVITY`, artifact
hashes, revision, and acceptance result. Episode artifacts no longer trust a freely typed
`owner: LOCAL_EDITOR` field as proof of authorship.

The engine rejects stale task IDs, unexpected situation IDs, modified input hashes,
out-of-order submissions, and attempts to replace an already locked situation without a
new repair task.

### Narration cues

One narration unit is no longer a single undifferentiated paragraph. Antigravity divides
it into ordered `NarrationCue` records:

- `cue_id`, `situation_id`, and `text`;
- one or more `claim_ids`;
- `visual_anchor_source_ms`, identifying when the described subject/action/result becomes
  visible;
- `anchor_kind`: `SETUP`, `CHARACTER_INTRO`, `CAUSE`, `ACTION`, `REVEAL`, `OUTCOME`, or
  `BRIDGE`;
- evidence frame and shot references;
- optional bounded `visual_preroll_ms` and `visual_postroll_ms`;
- the TTS duration after synthesis.

Every factual clause belongs to exactly one cue and every cue has a visual anchor. A cue
that introduces information not visible in the current range must cite transcript and
context evidence and use a setup image that does not contradict the narration.

### Newcomer context

The episode owns a `story_context.json` built incrementally by Antigravity and accepted by
the engine. It contains:

- characters already introduced, their short viewer-facing role, and relationships;
- story terms already explained;
- unresolved goals or threats needed for later situations;
- the last accepted causal outcome.

When a character or term first matters, the cue must introduce it in plain Vietnamese
before later cues use the bare name or jargon. The validator rejects a first bare mention
without an accepted introduction. Each situation must expose a structured causal chain:
`setup -> cause/goal -> meaningful action/decision -> outcome`, allowing irrelevant
steps to be omitted while preserving comprehension.

## Semantic timeline

TTS remains generated per cue, but cue audio is not concatenated back-to-back. The EDL
maps every visual anchor from source time to program time. The audio timeline then places
the cue at or after its mapped visual anchor.

Rules:

1. A `CHARACTER_INTRO`, `ACTION`, `REVEAL`, or `OUTCOME` cue must not start before its
   visual anchor. A tolerance of at most 100 milliseconds exists only for frame rounding.
2. The normal target is for the relevant image to establish itself 300–1,200 milliseconds
   before the descriptive words begin.
3. Setup narration may begin over its setup image but may not name a later reveal.
4. Silence or a previous non-conflicting cue may fill visual preroll. The engine never
   stretches a sentence backward to fill a clip.
5. If footage is too short for the voice at the allowed playback-rate range, Antigravity
   must shorten/rewrite the cue or select more relevant footage. The engine fails closed.
6. Cue order follows causal order. A result cue cannot start before its action cue and
   outcome anchor.

This replaces the current assumption that each unit's first video frame and first spoken
sample share the same semantic start.

## Validation and review gates

### Situation gate

Before a situation is locked, validators require:

- accepted Antigravity provenance for the current task and revision;
- transcript and frame evidence for every claim;
- valid keep/skip gaps and clean shot boundaries;
- introductions for new characters and terms;
- a complete causal chain appropriate to the situation;
- cue-to-anchor timing within the semantic rules;
- playback rate and TTS duration within policy;
- a situation contact sheet and timeline report.

Failure produces stable codes such as:

- `VOICE_PRECEDES_VISUAL_ANCHOR`;
- `CHARACTER_USED_BEFORE_INTRODUCTION`;
- `TERM_USED_BEFORE_EXPLANATION`;
- `CAUSAL_CHAIN_INCOMPLETE`;
- `EDITOR_PROVENANCE_INVALID`;
- `SITUATION_SUBMITTED_OUT_OF_ORDER`.

The repair packet names the exact cue, claim, spoken start, visual anchor, measured lead,
and referenced evidence. It goes to Antigravity, not Codex.

### Episode coherence gate

After all situations pass individually, a read-only episode audit checks chronology,
character naming, unresolved references, duplicated facts, repetitive filler transitions,
and continuity between the previous outcome and next setup. It emits findings for
Antigravity to repair. It cannot rewrite the script.

### Proxy gate

The state machine stops at `CHO_NGUOI_DUNG_DUYET_PROXY` after proxy validation. The proxy
package includes the video, a cue/anchor timeline, and a short list of story introductions.
Only `approve-proxy --run RUN_DIR` may advance to final rendering. A rejection records the
user's note, creates an Antigravity repair task, invalidates affected situations and their
downstream artifacts, and preserves the rejected proxy for comparison.

### Final gate

Final rendering reuses the approved plan, cue timeline, and source ranges. It may change
encoding quality only. If any editorial artifact hash differs from the approved proxy,
final rendering is refused and the workflow returns to proxy review.

## State machine

The local default path becomes:

1. `CHUAN_BI`
2. `TRICH_XUAT_BANG_CHUNG`
3. `CHO_ANTIGRAVITY_TINH_HUONG`
4. `KIEM_DINH_TINH_HUONG`
5. `TAO_TTS_TINH_HUONG`
6. `LAP_TIMELINE_TINH_HUONG`
7. `KIEM_DINH_NGU_NGHIA_TINH_HUONG`
8. repeat steps 3–7 for the next situation
9. `KIEM_DINH_MACH_TRUYEN_TOAN_TAP`
10. `DUNG_PROXY`
11. `KIEM_DINH_PROXY`
12. `CHO_NGUOI_DUNG_DUYET_PROXY`
13. `DUNG_VIDEO_CUOI`
14. `KIEM_DINH_ENGINE`
15. `HOAN_THANH`

Gemini Web remains an optional diagnostic command and cannot advance this state machine.

## BLACK TORCH migration and rerun

The current final and all existing evidence are preserved as rejected revision 1. The
engine marks the current plan and proxy as superseded, not deleted. Antigravity receives
a fresh revision-2 editor task using the same source, transcript, shots, and frames.

The rerun must specifically prove:

- unit 004 no longer speaks about the grandfather before his visual anchor near the
  corresponding source reveal;
- Jiro is introduced before the story uses his name as assumed knowledge;
- Rago, Mononoke, Hắc Tinh, Ichika, Shiba, and Onmitsu are introduced or explained before
  bare later use;
- transitions describe actual causality rather than rotate through filler phrases;
- the user approves the new proxy before any new final replaces the published path.

## Error handling and recovery

- Missing tools produce `CAN_CON_NGUOI_XU_LY` with the exact dependency and command that
  failed. The system never installs a dependency automatically.
- A failed Antigravity task remains resumable from its exact situation and revision.
- Two identical repair fingerprints with no artifact hash change stop the run instead of
  looping.
- A crash during acceptance cannot partially lock a situation: artifact writes and ledger
  append use a temporary staging directory and atomic replace.
- Rejected proxies and prior finals remain recoverable and are never overwritten in place.
- Codex engine changes occur only in the feature worktree until tests pass and the user
  chooses how to integrate the branch; existing dirty changes in the main checkout are
  preserved.

## Testing strategy

### Unit tests

- reject a cue whose spoken start precedes its visual anchor;
- accept bounded visual preroll and frame-rounding tolerance;
- reject a result spoken before its action/outcome anchor;
- reject a character or term used before introduction;
- reject stale or self-declared editor ownership without ledger provenance;
- reject out-of-order situation submission;
- require explicit proxy approval before final render;
- refuse final rendering when approved artifact hashes change.

### Integration tests

- reproduce the BLACK TORCH 28.728–35.786 second failure with a fixture and prove
  `VOICE_PRECEDES_VISUAL_ANCHOR`;
- run two situations sequentially through editor acceptance, TTS, cue placement, semantic
  validation, and proxy gating;
- reject a mechanically valid but newcomer-incomprehensible script;
- prove Antigravity repair invalidates only affected and downstream artifacts;
- preserve no-Gemini default execution.

### Runtime verification

- run the full test suite and Ruff in the feature worktree;
- let Antigravity author revision 2 rather than modifying its content in Codex;
- render and inspect the new proxy at the beginning, the 28–40 second region, the middle,
  and the ending;
- obtain explicit user proxy approval;
- render the final and verify streams, hashes, semantic report, and approved-plan identity;
- only then offer branch integration options.

## Acceptance criteria

The change is complete only when all of the following are true:

1. Antigravity provenance is required for every accepted editorial artifact.
2. Codex does not author or repair episode editorial content.
3. Cue-level semantic timing prevents narration from revealing a visual fact early.
4. New characters and terms are introduced before assumed use.
5. Each accepted situation has a comprehensible causal chain.
6. The whole-episode coherence audit passes without repetitive filler findings.
7. The BLACK TORCH regression at 30–35 seconds is fixed in a new proxy.
8. The user explicitly approves that proxy.
9. The final is rendered from exactly the approved editorial hashes.
10. Full tests and lint pass, and no pre-existing dirty main-checkout changes are lost.
