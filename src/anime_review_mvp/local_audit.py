from __future__ import annotations

import hashlib
from pathlib import Path

from .adaptive_edl import AdaptiveEdlDocument
from .editor_provenance import AcceptedEditorialRevision
from .errors import MvpError
from .jsonio import load_json
from .models import (
    AuditFinding,
    EngineAuditReport,
    FrameAnchorDocument,
)
from .render import RenderResult
from .review_contracts import LoudnessReport
from .semantic_timeline import SemanticTimeline, semantic_timing_findings
from .situation_validation import (
    coherence_findings,
    validate_causal_chains,
    validate_semantic_range,
)
from .situations import (
    CueTtsManifest,
    EditorialPolicy,
    NarrationPlan,
    SemanticReviewDocument,
    SituationDocument,
    SituationTtsManifest,
    StoryContext,
)
from .story_context import validate_newcomer_context


def _anchor_ids(document: FrameAnchorDocument, timeline: str) -> set[str]:
    if any(item.timeline != timeline for item in document.anchors):
        raise MvpError(f"{timeline.lower()} anchor document contains another timeline")
    identifiers = [item.anchor_id for item in document.anchors]
    if len(identifiers) != len(set(identifiers)):
        raise MvpError("anchor IDs must be unique")
    return set(identifiers)


def _validate_semantic_review(
    review: SemanticReviewDocument,
    plan: NarrationPlan,
    source_anchors: FrameAnchorDocument,
    program_anchors: FrameAnchorDocument,
) -> SemanticReviewDocument:
    expected = tuple(item.unit_id for item in plan.units)
    observed = tuple(item.unit_id for item in review.units)
    if expected != observed or len(set(observed)) != len(observed):
        raise MvpError("semantic review unit IDs must exactly match narration units")
    source_ids = _anchor_ids(source_anchors, "SOURCE")
    program_ids = _anchor_ids(program_anchors, "PROGRAM")
    for item in review.units:
        if not set(item.source_frame_refs) <= source_ids:
            raise MvpError("semantic review references an unknown source anchor")
        if not set(item.program_frame_refs) <= program_ids:
            raise MvpError("semantic review references an unknown program anchor")
    return review


def load_semantic_review(
    path: Path,
    plan: NarrationPlan,
    source_anchors: FrameAnchorDocument,
    program_anchors: FrameAnchorDocument,
) -> SemanticReviewDocument:
    review = load_json(path, SemanticReviewDocument)
    return _validate_semantic_review(review, plan, source_anchors, program_anchors)


def content_fingerprint(paths: tuple[Path, ...]) -> str:
    if not paths:
        raise MvpError("content fingerprint requires artifact paths")
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: str(item.resolve()).casefold()):
        if not path.is_file():
            raise MvpError(f"fingerprint artifact does not exist: {path}")
        digest.update(str(path.resolve()).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _finding(code: str, message: str, unit_id: str | None = None) -> AuditFinding:
    return AuditFinding("ERROR", code, unit_id, message, ())


def build_local_audit(
    plan: NarrationPlan,
    situations: SituationDocument,
    semantic_review: SemanticReviewDocument,
    source_anchors: FrameAnchorDocument,
    program_anchors: FrameAnchorDocument,
    edl: AdaptiveEdlDocument,
    tts: SituationTtsManifest,
    render: RenderResult,
    *,
    policy: EditorialPolicy | None = None,
) -> EngineAuditReport:
    _validate_semantic_review(semantic_review, plan, source_anchors, program_anchors)
    active_policy = policy or EditorialPolicy()
    findings: list[AuditFinding] = []
    if not (plan.policy_version == situations.policy_version == tts.policy_version):
        findings.append(
            _finding("POLICY_MISMATCH", "Situation, narration, and TTS policies differ.")
        )

    situation_ids = {item.situation_id for item in situations.situations}
    if any(unit.situation_id not in situation_ids for unit in plan.units):
        findings.append(_finding("UNKNOWN_SITUATION", "Narration references an unknown situation."))

    for item in semantic_review.units:
        if not item.supported:
            for code in item.finding_codes:
                findings.append(_finding(code, item.note, item.unit_id))

    expected_units = tuple(item.unit_id for item in plan.units)
    if tuple(item.unit_id for item in tts.units) != expected_units:
        findings.append(_finding("TTS_UNIT_MISMATCH", "TTS units do not match narration units."))
    if tuple(dict.fromkeys(item.unit_id for item in edl.segments)) != expected_units:
        findings.append(_finding("EDL_UNIT_MISMATCH", "EDL units do not match narration units."))
    if edl.total_duration_ms != tts.total_duration_ms:
        findings.append(_finding("TTS_EDL_DRIFT", "TTS and EDL durations differ."))
    if render.video_stream_count != 1 or render.audio_stream_count != 1:
        findings.append(
            _finding(
                "STREAM_COUNT_INVALID",
                "Render must have one video and one audio stream.",
            )
        )
    if render.drift_ms > 80 or abs(render.duration_ms - edl.total_duration_ms) > 80:
        findings.append(_finding("RENDER_DRIFT", "Rendered audio/video timing exceeds 80 ms."))
    if any(
        not active_policy.minimum_playback_rate
        <= item.playback_rate
        <= active_policy.maximum_playback_rate
        for item in edl.segments
    ):
        findings.append(_finding("PLAYBACK_RATE_INVALID", "EDL playback rate is outside policy."))

    source_units = {item.span_id for item in source_anchors.anchors}
    program_units = {item.span_id for item in program_anchors.anchors}
    for unit_id in expected_units:
        if unit_id not in source_units or unit_id not in program_units:
            findings.append(
                _finding(
                    "MISSING_FRAME_ANCHOR",
                    "Unit lacks source or program frame evidence.",
                    unit_id,
                )
            )

    supported = sum(item.supported for item in semantic_review.units)
    coverage = supported / len(semantic_review.units)
    return EngineAuditReport(not findings, f"{coverage:g}", tuple(findings))


def _mvp_error_finding(error: MvpError) -> AuditFinding:
    message = str(error)
    code = message.split(":", 1)[0]
    return _finding(code, message)


def build_episode_coherence_audit(
    plan: NarrationPlan,
    situations: SituationDocument,
    initial_context: StoryContext,
) -> EngineAuditReport:
    findings: list[AuditFinding] = list(coherence_findings(plan, situations))
    try:
        validate_causal_chains(situations)
    except MvpError as exc:
        findings.append(_mvp_error_finding(exc))
    try:
        validate_newcomer_context(plan, initial_context)
    except MvpError as exc:
        findings.append(_mvp_error_finding(exc))
    for unit in plan.units:
        for source_range in unit.evidence_ranges:
            try:
                validate_semantic_range(source_range)
            except MvpError as exc:
                findings.append(_mvp_error_finding(exc))
    return EngineAuditReport(not findings, "1" if not findings else "0", tuple(findings))


def build_v2_local_audit(
    plan: NarrationPlan,
    situations: SituationDocument,
    timeline: SemanticTimeline,
    tts: CueTtsManifest,
    edl: AdaptiveEdlDocument,
    render: RenderResult,
    provenance: tuple[AcceptedEditorialRevision, ...],
    initial_context: StoryContext,
    loudness: LoudnessReport | None = None,
) -> EngineAuditReport:
    findings = list(build_episode_coherence_audit(plan, situations, initial_context).findings)
    policy = EditorialPolicy()
    if not policy.target_minimum_ms <= render.duration_ms <= policy.target_maximum_ms:
        findings.append(
            _finding(
                "PRODUCTION_DURATION_OUT_OF_RANGE",
                "Production proxy must be between 7 and 12 minutes.",
            )
        )
    situation_ids = {item.situation_id for item in situations.situations}
    proven = {
        item.situation_id
        for item in provenance
        if item.actor == "ANTIGRAVITY" and item.revision >= 1
    }
    if proven != situation_ids:
        findings.append(
            _finding(
                "EDITOR_PROVENANCE_INVALID",
                "Every situation must have an accepted Antigravity revision.",
            )
        )

    plan_cues = tuple(cue for unit in plan.units for cue in unit.cues)
    expected_ids = tuple(cue.cue_id for cue in plan_cues)
    tts_ids = tuple(cue.cue_id for cue in tts.cues)
    timeline_ids = tuple(cue.cue_id for cue in timeline.cues)
    if not (expected_ids == tts_ids == timeline_ids):
        findings.append(_finding("CUE_ID_MISMATCH", "Plan, TTS, and timeline cue IDs differ."))

    cue_by_id = {cue.cue_id: cue for cue in plan_cues}
    anchor_by_id = {item.cue_id: item.visual_anchor_program_ms for item in timeline.cues}
    for timing_finding in semantic_timing_findings(timeline.cues, timeline.total_duration_ms):
        cue = cue_by_id.get(timing_finding.cue_id or "")
        evidence = (
            ()
            if cue is None
            else (
                *cue.frame_refs,
                f"program-anchor-ms:{anchor_by_id[cue.cue_id]}",
            )
        )
        findings.append(
            AuditFinding(
                timing_finding.severity,
                timing_finding.code,
                timing_finding.cue_id,
                timing_finding.message,
                evidence,
            )
        )
    if edl.total_duration_ms != timeline.total_duration_ms:
        findings.append(_finding("EDL_TIMELINE_DRIFT", "EDL and semantic timeline differ."))
    if abs(render.duration_ms - timeline.total_duration_ms) > 80 or render.drift_ms > 80:
        findings.append(
            _finding("RENDER_DRIFT", "Render differs from semantic timeline by over 80 ms.")
        )
    if render.video_stream_count != 1 or render.audio_stream_count != 1:
        findings.append(_finding("STREAM_COUNT_INVALID", "Render must have one video and audio."))
    if loudness is not None and (
        not -15.0 <= loudness.integrated_lufs <= -13.0
        or loudness.true_peak_dbtp > -1.5
        or loudness.loudness_range_lu > 7.0
    ):
        findings.append(
            _finding(
                "NARRATION_LOUDNESS_OUT_OF_RANGE",
                "Narration loudness must be -14 LUFS ±1, TP <= -1.5 dBTP, LRA <= 7 LU.",
            )
        )
    return EngineAuditReport(not findings, "1" if not findings else "0", tuple(findings))
