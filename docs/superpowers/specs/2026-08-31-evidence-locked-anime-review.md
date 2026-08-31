# Evidence-Locked Anime Review Design

## Goal

Make Antigravity the sole episode editor while the local engine enforces a 7–12 minute, continuously narrated anime review whose spoken claims match the exact source and proxy images shown at that moment.

## Non-negotiable boundaries

- Codex changes engine logic, schemas, prompts, workflow, and validators only.
- Antigravity inspects the source video, transcript/SRT, shots, frames, and reference video; it alone divides situations, writes narration, chooses footage, renders, and performs semantic review.
- A production proxy and final render must be 420,000–720,000 ms.
- Review narration uses natural short pauses; no important clip may play without narration and surplus footage is removed.
- Opening, ending, credits, preview, advertisements, non-story title cards, junk frames, flashes, and transition debris are excluded.
- Every cue is evidence-locked to its own source interval, transcript/SRT references, shots, and source/program frames.
- The engine never repairs an editorial mismatch by compacting or remapping accepted footage after the fact.
- Missing tools stop the workflow with the exact required tool; the engine never silently installs anything.

## Architecture

### Reference profile

The run records a required reference video path and SHA-256. Before episode structure work, Antigravity receives a reference-analysis task and records an evidence-backed style profile. The reference controls pacing and narration continuity, not story content or absolute duration. For the approved reference, natural inter-phrase pauses are generally around 0.48–0.60 seconds; production policy permits 0.35–0.90 seconds normally and rejects inter-cue gaps above 1.20 seconds.

### Episode budget

Before situation editing begins, Antigravity produces an episode editorial budget allocating duration and narration across retained situations by plot importance. Predicted TTS duration plus permitted pauses must fit 420,000–720,000 ms. A preferred 480,000–600,000 ms band guides editing but is not a hard failure.

### Evidence-locked cues

Each narration cue owns a source interval rather than inheriting the entire situation range. Its interval must contain one coherent semantic event and include its visual anchor. Transcript/SRT references are mandatory when relevant dialogue exists; visual-only cues require shots and frames. After TTS, the timeline may choose an allowed playback rate but may not trim, merge, or remap the accepted cue interval.

### Continuous timeline

Cues are laid out sequentially with 80–900 ms natural inter-cue pauses, at most 1,200 ms. Leading and trailing narration silence are at most 1,200 ms. Footage outside cue-locked intervals is absent unless explicitly justified as a short narrative transition. Timeline failure routes the responsible situation back to Antigravity instead of modifying editorial content.

### Independent verification

Proxy evidence is generated per cue from the cue's exact source and program intervals. The verifier compares cue text, transcript/SRT, source frames, and actual proxy frames at START, ANCHOR, MIDDLE, and END. Every cue must be MATCH. It also checks excluded-content boundaries, 7–12 minute duration, narration gaps/coverage, measured loudness, and cue-to-cue level consistency. Any failure routes only the responsible scope back to Antigravity; the engine cannot self-PASS.

### Current run handling

Existing accepted narration and proxy artifacts were produced under an invalid contract and must not seed the new edit. Migration archives or invalidates the editorial chain, preserves source analysis inputs, records the reference, and schedules a fresh autonomous Antigravity pass. The user sends one tagged prompt; the operator loops until `CHO_NGUOI_DUNG_DUYET_PROXY`.
