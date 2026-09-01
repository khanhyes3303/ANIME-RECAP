# In-Place Whole-Episode Review Design

## Goal

Simplify the existing Antigravity anime-review pipeline in place so one episode is
edited as one coherent story, produces a 7–12 minute proxy, survives reconnects,
and reuses the source-analysis, TTS-cache, timeline, render, and proxy safeguards
that already work.

## Decision

The project will not add a parallel pipeline. The current situation-v2 path will
become a whole-episode path. Legacy enum values and loaders may remain temporarily
for old archives, but the operator will no longer route new work through a
producer/TTS/timeline/verifier loop for every situation.

The existing artifact locations remain canonical:

- `situation_index.json`
- `Kho_Anime/.../Su_that/situations.json`
- `Kho_Anime/.../Kich_ban/narration_plan.json`
- `adaptive_edl.json`
- `semantic_timeline.json`
- `cue_tts_manifest.json`
- `proxy/review_proxy.mp4`

## What Remains

- Source probing and immutable `source_ref.json`.
- Transcript/SRT ingestion, shot detection, and frame extraction.
- `situation_index.json` for chronological boundaries and excluded material.
- Existing narration cue, claim, evidence-range, EDL, and timeline models.
- Content-addressed TTS cache per cue.
- Playback-rate fitting between `0.80x` and `1.30x`.
- Proxy renderer, publisher-bumper guard, loudness checks, and user approval.
- Atomic `run_state.json` checkpoint writes and code/policy identity checks.

## What Leaves the Canonical Flow

- One editor task per situation.
- `locked_situation_ids` as a prerequisite for progress.
- TTS and timeline construction after each situation.
- An independent Antigravity verifier task for every situation.
- Repeated revision directories for local situation retries.
- A final duration failure routed only to the last situation.
- `GOAL_COMPLETE` before `proxy/review_proxy.mp4` exists and the state reaches
  `CHO_NGUOI_DUNG_DUYET_PROXY`.

## Canonical State Flow

The operator exposes this sequence:

1. `CHUAN_BI`
2. `TRICH_XUAT_BANG_CHUNG`
3. `CHO_ANTIGRAVITY_CHIA_TINH_HUONG`
4. `KIEM_DINH_CHI_MUC_TINH_HUONG`
5. `CHO_ANTIGRAVITY_TINH_HUONG` — one whole-episode editorial task
6. `KIEM_DINH_TINH_HUONG` — one global content validation
7. `TAO_TTS_TINH_HUONG` — one cache-aware TTS pass
8. `LAP_TIMELINE_TINH_HUONG` — one full timeline pass
9. `KIEM_DINH_MACH_TRUYEN_TOAN_TAP`
10. `DUNG_PROXY`
11. `KIEM_DINH_PROXY`
12. `CHO_NGUOI_DUNG_DUYET_PROXY`

Legacy stages remain readable for archived runs but are not emitted for a new or
migrated run.

## Antigravity Editorial Task

After the accepted situation index, the engine creates one task with
`situation_id="__episode__"`. It reuses the editor-task provenance mechanism and
adds the task kind `EPISODE_REVIEW`.

The task receives:

- The accepted situation index.
- Transcript/SRT references for the complete episode.
- Shot metadata and frame manifest.
- The reference style profile.
- The editorial duration and playback-rate policy.
- A compact JSON schema/example for the two required drafts.

It writes exactly:

- `situations_draft.json`, containing all editable situations in source order.
- `narration_draft.json`, containing all narration units, claims, cues, and kept
  evidence ranges in the same order.

Antigravity must inspect referenced frames directly. It must not create scripts to
manufacture editorial JSON, inspect validator implementation, or claim completion.
Its only terminal action is to submit the two drafts with the provided acceptance
command.

## Global Acceptance Rules

Acceptance occurs before any TTS call and is transactional: both drafts either
become canonical together or neither does.

The engine rejects a submission unless:

- Every editable index entry appears exactly once and in source order.
- Excluded index entries never appear in kept ranges.
- Every cue belongs to its declared unit and situation.
- Every range stays within its indexed source boundary and uses known shots,
  frames, and overlapping transcript/SRT references.
- Narration remains grounded in its claim and evidence instead of describing a
  later or earlier situation.
- Bridges and narration do not repeat boilerplate templates.
- The planned narration has enough substantive words for a plausible 7–12 minute
  voice and no cue exceeds the existing readability ceiling.

The early word-budget check is only a fast guard. Exact duration is decided from
the synthesized WAV files.

## TTS and Duration Repair

After global acceptance, the engine synthesizes every cue once. Existing
content-addressed cache keys remain unchanged, so a revised episode reuses every
unchanged cue.

The exact sum of cue durations must fall between `420000` and `720000` ms. If it
does not, the engine returns the complete episode to one new `EPISODE_REVIEW`
revision with `EPISODE_VOICE_BUDGET_TOO_SHORT` or
`EPISODE_VOICE_BUDGET_TOO_LONG`. No situation is locked, and Antigravity receives
the current complete drafts plus the measured duration. It expands or trims the
story across the episode rather than padding the final scene.

Timeline and rendering never start while the voice budget is invalid.

## Timeline and Proxy

The existing semantic timeline builder remains responsible for aligning each cue
to its accepted visual anchor. It may fit clips using playback rates from `0.80x`
through `1.30x`; it may not reorder source events or pull footage from another
situation.

One EDL, one aligned narration track, and one proxy are produced for the episode.
The existing machine proxy audit checks artifact identity, duration, loudness,
excluded visual content, cue coverage, and A/V timing. A separate per-cue
Antigravity verifier is removed from the canonical path. The user is the final
semantic reviewer at `CHO_NGUOI_DUNG_DUYET_PROXY`.

## Repair and Resume

All failures route to one of two owners:

- Editorial/content/duration errors return to the active whole-episode task.
- Missing tools or two byte-identical failed submissions reach
  `CAN_CON_NGUOI_XU_LY` with a concrete error code.

The state stores one active task ID and its input hash. On reconnect, `operator`
reuses that exact task. It never creates another task while one is active and never
accepts a submission whose task, input, policy, or source hash differs.

Completed source analysis and cached cue audio survive reconnects. Partial staging
files are not canonical and can be overwritten by the same active task.

## Migration of the Current Run

The current partial 4-minute editorial chain is not promoted. Migration will:

1. Archive its editorial drafts, TTS derivatives, audits, status files, and proxy
   attempts under the existing `revisions` directory.
2. Preserve source video references, transcript/SRT, shots, frames, and the
   accepted source cache.
3. Clear per-situation locks and repair history.
4. Reuse a valid chronological situation index if it still matches the current
   source and code policy; otherwise request one structure task.
5. Create one fresh whole-episode editorial task.

## Success Criteria

- A normal episode needs at most one structure submission and one whole-episode
  editorial submission before TTS.
- No TTS or timeline command runs between individual situations.
- A 4-minute script is rejected before rendering and is repairable as a whole.
- Disconnecting before or after submission resumes the same task without losing
  accepted work or duplicating TTS calls.
- The only newly delivered MP4 is `proxy/review_proxy.mp4` outside `revisions`.
- The operator cannot report completion without that file and state
  `CHO_NGUOI_DUNG_DUYET_PROXY`.
- Existing automated tests remain green, and new tests cover the simplified happy
  path, whole-episode duration repair, reconnect idempotency, and current-run
  migration.

## Non-Goals

- Replacing FFmpeg, the TTS provider, shot detection, or frame extraction.
- Adding a second application or external database.
- Automatically publishing a final video without user proxy approval.
- Lowering the requested minimum duration below seven minutes.
