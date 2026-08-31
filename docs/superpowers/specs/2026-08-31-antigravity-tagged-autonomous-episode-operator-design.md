# Antigravity Tagged Autonomous Episode Operator Design

## Goal

Build a reusable, fail-closed workflow for any anime episode in which Antigravity is
the sole editorial worker from source understanding through proxy review, while Codex
only maintains the engine, schemas, validators, and operator. The user tags
`teamwork-preview` and `goal` once, sends one generated launch prompt, and is not asked
to copy or relay individual situation tasks.

The workflow cannot promise that a perceptual model will never make a judgment error.
It must instead guarantee that no situation, cue, excluded interval, or measurable
render defect can silently pass without the required evidence and validation record.

## Authority Boundary

Antigravity owns all episode-specific editorial decisions:

- watching and understanding the source video;
- reading transcript/SRT, shots, and extracted frames;
- dividing the episode into a dynamic number of situations;
- deciding which situations and source ranges carry story information;
- excluding intro, opening, ending, credits, recap, preview, advertisements, and
  decorative footage that does not carry required story information;
- writing Vietnamese review narration and continuity bridges;
- selecting source ranges and visual anchors;
- reviewing the rendered proxy cue by cue against frames and transcript/SRT;
- revising failed situations until they pass or the no-progress guard stops the run.

Codex and the local engine may not write narration, choose source ranges, reclassify
story events, or substitute their own interpretation of the episode. Their authority is
limited to:

- generating scoped jobs and evidence packets;
- validating schemas, hashes, references, timing, coverage, loudness, and render
  integrity;
- dispatching the next Antigravity job automatically;
- routing a failed check back to the exact situation or cue;
- stopping safely when required capabilities or tools are missing;
- maintaining and testing the operator itself.

Gemini Web is not part of the default workflow.

## User Contract and Tagged Launch

The user performs one launch action for an episode:

1. Open a new Antigravity conversation in the saved project.
2. Attach the `teamwork-preview` and `goal` tags.
3. Send the complete contents of the generated `PROMPT_GUI_ANTIGRAVITY.txt` once.

The launch prompt defines one persistent goal: advance the named run from its current
state to `CHO_NGUOI_DUNG_DUYET_PROXY`. Completing one structure or situation task does
not complete this goal.

`teamwork-preview` is used for internal separation of duties. It does not broaden file
permissions or allow multiple workers to write the same artifact. The Antigravity parent
coordinates these roles:

- **Evidence analyst:** examines source video, transcript/SRT, shots, and frames and
  prepares the situation structure.
- **Situation editor:** edits one active situation at a time and creates only its
  required drafts.
- **Independent verifier:** reviews evidence and rendered program material without
  editing the producer's artifacts; it returns structured findings only.

If either tagged capability is unavailable after launch, Antigravity must report
`ANTIGRAVITY_CAPABILITY_MISSING` and stop. Codex must not silently take over the
editorial work.

## Dynamic Episode Model

The number of situations is determined by the source episode and is never configured as
a fixed count. A 20-situation episode and a 70-situation episode use the same operator.

The structure pass must cover the source timeline continuously from 0 to the measured
source duration with no gaps and no overlaps. Situation boundaries must snap to shot
boundaries so that every source shot belongs to exactly one indexed situation. Every
situation includes existing transcript segment references when relevant and existing
frame references. A visual-only situation is valid only when it is explicitly marked as
visual-only and supported by shot and frame evidence.

Every indexed interval is either editable or excluded. Excluded intervals require a
specific reason. Cold opens and post-credit scenes that contain story information are
editable; title cards or music sequences are not excluded merely by position, so
Antigravity must decide from their semantic content.

## Autonomous Operator Loop

The engine exposes one resumable operator command for Antigravity. The loop reads
`run_state.json` and `next_action.json`, performs exactly the action allowed by the
current state, validates the result, and continues without another user message.

The loop is:

1. Verify required tools and tagged-launch contract.
2. Prepare transcript/SRT, shot boundaries, frame manifests, and source metadata.
3. Dispatch one `STRUCTURE` job to the evidence analyst.
4. Accept the structure only after coverage and reference validation.
5. For each non-excluded situation in source order:
   1. generate a scoped evidence packet;
   2. dispatch one `SITUATION` job to the situation editor;
   3. validate its drafts locally;
   4. dispatch a separate semantic verification job;
   5. lock the situation only when both validation layers pass;
   6. otherwise create a new revision for only the failed situation and continue.
6. Generate TTS, semantic timeline, and adaptive EDL from the accepted artifacts.
7. Render the proxy with normalized narration audio.
8. Generate proxy evidence packets for every narration cue.
9. Dispatch one `PROXY_AUDIT` job to the independent verifier.
10. Route every finding to its exact situation/cue and repeat affected downstream
    stages.
11. Stop at `CHO_NGUOI_DUNG_DUYET_PROXY` only after all proxy checks pass.

Each action is idempotent. Restarting the operator resumes from the committed state and
does not redo a locked situation whose input fingerprint is unchanged.

## Job Contracts

Every job contains `task_kind`, `task_id`, `revision`, `input_sha256`,
`required_outputs`, `allowed_staging_dir`, and exact input paths. Antigravity may only
write the declared outputs into the declared staging directory.

Supported task kinds are:

- `STRUCTURE`: outputs only `situation_index_draft.json`.
- `SITUATION`: outputs only `situation_draft.json` and `narration_draft.json`.
- `SITUATION_AUDIT`: outputs only `situation_audit_draft.json`.
- `PROXY_AUDIT`: outputs only `proxy_audit_draft.json`.

The independent verifier cannot modify producer drafts. A failing audit produces
finding codes and evidence references; the operator creates the next producer revision.

## Situation-Level Evidence and Quality Gates

Each narration cue must identify:

- one situation and one factual claim;
- source start/end and a visual anchor timestamp;
- all intersecting shot IDs;
- frame references proving the event, including the anchor frame;
- overlapping transcript/SRT references when dialogue is relevant;
- an explicit visual-only justification when no transcript applies;
- the relationship to the previous and next cue.

Each kept range carries exactly one semantic event, action phase, and story purpose.
Different approach, action, reaction, or outcome meanings require separate ranges even
inside the same fight or conversation. The validator rejects mixed-semantic ranges,
micro-clips, micro-gaps, missing intersecting shots, invalid references, and narration
that assumes knowledge not previously introduced.

The independent situation audit compares the cue text against its transcript/SRT and
frames. It must return one verdict per cue, never a single blanket PASS for a situation.
All cue verdicts must pass before the situation is locked.

## Proxy Evidence and Semantic Audit

For every cue, the engine extracts program frames at:

- the beginning of the visual range;
- the visual anchor;
- the midpoint;
- the end of the visual range.

The proxy audit packet also includes the corresponding source frames, source
transcript/SRT overlap, cue text, spoken interval, source range, and program range.
Antigravity's independent verifier must compare these items and return:

- `MATCH`, `MISMATCH`, or `INSUFFICIENT_EVIDENCE`;
- observed visual action and visible characters;
- narration meaning;
- transcript/SRT support or visual-only justification;
- whether the voice begins before the event appears;
- whether the range contains more than one semantic situation;
- exact repair references for any failure.

The engine accepts the proxy only when every cue has a valid evidence-backed `MATCH`.
Missing audit entries, duplicate cue IDs, unverifiable references, or a blanket summary
fail closed.

## Intro, Opening, Ending, and Frame-Quality Gates

All excluded situation ranges are forbidden source intervals in the EDL. The validator
must reject any overlap, including a single-frame overlap caused by rounding.

The proxy audit includes dedicated beginning and ending boundary packets. Antigravity
checks the first kept sequence and last kept sequence against source frames and
transcript/SRT to confirm that no non-story intro, opening, ending, credits, or preview
survives. The engine additionally detects black frames, frozen padding beyond the
timeline tolerance, flashes, sub-minimum fragments, and cut points that cross excluded
shot boundaries.

## Audio and Synchronization Gates

The render pipeline normalizes narration using a two-pass loudness measurement. The
default delivery target is -14 LUFS integrated loudness, true peak no higher than
-1.5 dBTP, and loudness range no greater than 7 LU. The generated loudness report is an
input to the proxy audit.

The engine rejects:

- missing or duplicate audio/video streams;
- audio/video duration drift above 80 ms;
- a cue whose narration begins more than 100 ms before its visual anchor;
- clipped samples, inaudible narration, or loudness outside the configured tolerance;
- narration whose speech interval extends beyond its accepted visual evidence.

Antigravity still performs the semantic/listening review. Objective engine measurements
do not replace its responsibility to judge whether speech, scene, and story meaning fit.

## Failure Routing and Stop Conditions

A failure contains an owner, task kind, situation ID, cue ID when applicable, finding
codes, evidence references, and an input/output fingerprint. The operator retries only
after producing a new revision with a changed output fingerprint.

The autonomous run stops only when:

- a named required tool or tagged capability is unavailable;
- the same finding set and output fingerprint recur for two consecutive repair rounds;
- input files change after a job is issued;
- a schema or provenance violation indicates unsafe state;
- the proxy has passed and awaits user approval.

When stopped, `next_action.json` contains one precise code and installation or repair
instruction. It never asks the user to copy the next situation prompt.

## User Approval and Final Output

The user reviews one proxy after Antigravity's full proxy audit passes. Approval proceeds
to final render and final engine integrity audit. Rejection names one or more situations
or cues, returns them to Antigravity, and automatically rebuilds only affected downstream
artifacts.

The final artifact remains:

`Kho_Anime/<Anime>/Mua_XX/Tap_XXX/Thanh_pham/review_anime.mp4`

## Compatibility and Migration

Existing accepted Antigravity revisions remain immutable. An existing run may enter the
new operator from its current valid state. Runs with an already rejected proxy create
new situation or proxy-audit revisions; no accepted source evidence is deleted.

The operator supports episodes with variable duration, frame rate, resolution,
subtitle language, sparse dialogue, or visual-only scenes. Missing transcript/SRT is
not silently treated as success: Antigravity must provide visual-only evidence for each
affected cue.

## Verification Strategy

Implementation uses test-driven development and includes:

- unit tests for state transitions, job contracts, dynamic situation counts, exact
  coverage, excluded-range EDL blocking, cue evidence completeness, and no-progress
  guards;
- contract tests proving Codex cannot author editorial artifacts and verifier jobs cannot
  modify producer artifacts;
- integration tests with a fake Antigravity adapter that processes arbitrary situation
  counts without user prompts;
- failure-injection tests for stale inputs, missing tags/tools, invalid frames,
  mismatched transcript references, intro leakage, low loudness, and visual lead;
- FFmpeg integration tests for loudness, stream count, duration drift, frame rounding,
  and excluded-interval boundaries;
- one end-to-end fixture that reaches `CHO_NGUOI_DUNG_DUYET_PROXY` through a single
  tagged launch and demonstrates resumability after interruption.

No implementation is considered complete merely because tests pass. A real episode
run must also produce a proxy audit with complete per-cue evidence and stop at the user
approval gate.
