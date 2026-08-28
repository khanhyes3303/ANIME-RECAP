from __future__ import annotations

from decimal import Decimal

from .errors import MvpError
from .models import (
    AtomicStoryboard,
    AtomicTtsManifest,
    AuditFinding,
    CodexSemanticReview,
    CriticReviewDocument,
    EngineAuditReport,
    FrameAnchor,
    FrameAnchorDocument,
    NarrationSpanDocument,
    SpanTtsManifest,
)
from .render import RenderResult

_POSITIONS = {"START", "MIDDLE", "END"}
_BLOCKING_SEMANTIC_CODES = {
    "ACTION_MISMATCH",
    "FACT_CONTRADICTION",
    "MISSING_MAIN_PLOT",
    "SCENE_MISMATCH",
    "VOICE_AHEAD",
    "VOICE_BEHIND",
}


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise MvpError(f"{label} IDs must be unique")


def _anchor_map(
    anchors: FrameAnchorDocument,
    timeline: str,
) -> dict[str, tuple[FrameAnchor, ...]]:
    grouped: dict[str, list[FrameAnchor]] = {}
    for anchor in anchors.anchors:
        if anchor.timeline != timeline:
            raise MvpError(f"{timeline} anchor document contains another timeline")
        grouped.setdefault(anchor.span_id, []).append(anchor)
    return {span_id: tuple(items) for span_id, items in grouped.items()}


def _coverage_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def build_engine_audit(
    spans: NarrationSpanDocument,
    tts: SpanTtsManifest,
    review: CodexSemanticReview,
    source_anchors: FrameAnchorDocument,
    final_anchors: FrameAnchorDocument,
    render: RenderResult,
) -> EngineAuditReport:
    if spans.owner != "CODEX":
        raise MvpError("locked narration owner must be CODEX")
    if review.owner != "CODEX":
        raise MvpError("semantic review owner must be CODEX")

    span_ids = [span.span_id for span in spans.spans]
    review_ids = [item.span_id for item in review.spans]
    tts_ids = [item.span_id for item in tts.spans]
    _unique(span_ids, "locked span")
    _unique(review_ids, "semantic review")
    _unique(tts_ids, "TTS span")
    if set(span_ids) != set(review_ids) or set(span_ids) != set(tts_ids):
        raise MvpError("locked spans, TTS, and semantic review IDs must match")

    source_by_span = _anchor_map(source_anchors, "SOURCE")
    final_by_span = _anchor_map(final_anchors, "PROGRAM")
    review_by_span = {item.span_id: item for item in review.spans}
    duration_by_span = {item.span_id: item.duration_ms for item in tts.spans}

    findings: list[AuditFinding] = []
    supported_ms = 0
    total_ms = sum(duration_by_span.values())
    for span_id in span_ids:
        source = source_by_span.get(span_id, ())
        final = final_by_span.get(span_id, ())
        if {item.position for item in source} != _POSITIONS:
            raise MvpError(f"source anchors are incomplete for {span_id}")
        if {item.position for item in final} != _POSITIONS:
            raise MvpError(f"program anchors are incomplete for {span_id}")
        item = review_by_span[span_id]
        required_evidence = {anchor.anchor_id for anchor in (*source, *final)}
        if not required_evidence <= set(item.evidence_anchor_ids):
            raise MvpError(f"semantic review lacks source/program evidence for {span_id}")
        if item.supported:
            supported_ms += duration_by_span[span_id]
        for code in item.finding_codes:
            findings.append(
                AuditFinding(
                    "ERROR" if code in _BLOCKING_SEMANTIC_CODES else "WARNING",
                    code,
                    span_id,
                    item.note,
                    item.evidence_anchor_ids,
                )
            )

    coverage = Decimal(supported_ms) / Decimal(total_ms)
    if coverage < Decimal("0.80"):
        findings.append(
            AuditFinding(
                "ERROR",
                "DIRECT_EVIDENCE_BELOW_80",
                None,
                "Direct visual evidence coverage is below 0.80.",
                (),
            )
        )
    if not 420_000 <= render.duration_ms <= 720_000:
        findings.append(
            AuditFinding(
                "ERROR",
                "REVIEW_DURATION_OUT_OF_RANGE",
                None,
                "Final review duration must be between 420 and 720 seconds.",
                (),
            )
        )
    if render.video_stream_count != 1 or render.audio_stream_count != 1:
        findings.append(
            AuditFinding(
                "ERROR",
                "FINAL_STREAM_LAYOUT_INVALID",
                None,
                "Final review must contain one video and one TTS audio stream.",
                (),
            )
        )
    if render.drift_ms > 80 or abs(total_ms - render.audio_duration_ms) > 80:
        findings.append(
            AuditFinding(
                "ERROR",
                "AUDIO_VIDEO_DRIFT",
                None,
                "Rendered audio/video or TTS manifest drift exceeds 80 ms.",
                (),
            )
        )

    passed = not any(finding.severity == "ERROR" for finding in findings)
    return EngineAuditReport(passed, _coverage_text(coverage), tuple(findings))


def build_atomic_engine_audit(
    storyboard: AtomicStoryboard,
    tts: AtomicTtsManifest,
    critic: CriticReviewDocument,
    render: RenderResult,
    *,
    expected_policy_sha256: str,
    actual_policy_sha256: str,
) -> EngineAuditReport:
    beat_ids = [beat.beat_id for beat in storyboard.beats]
    tts_ids = [beat.beat_id for beat in tts.beats]
    review_ids = [item.beat_id for item in critic.beat_reviews]
    _unique(beat_ids, "atomic beat")
    _unique(tts_ids, "atomic TTS beat")
    _unique(review_ids, "critic beat")
    if set(beat_ids) != set(tts_ids) or set(beat_ids) != set(review_ids):
        raise MvpError("storyboard, atomic TTS, and critic beat IDs must match")
    if critic.phase != "VIDEO":
        raise MvpError("final atomic audit requires VIDEO critic phase")
    if critic.producer_context_id != storyboard.producer_context_id:
        raise MvpError("critic producer context does not match storyboard")
    if critic.critic_context_id == critic.producer_context_id:
        raise MvpError("producer and critic require separate contexts")

    blocking_codes = _BLOCKING_SEMANTIC_CODES | {
        "WRONG_CHARACTER",
        "INVENTED_MOTIVE",
        "MULTI_ACTION_BEAT",
        "LOW_VALUE_FOOTAGE",
        "MISSING_EVIDENCE",
        "TTS_TOO_LONG",
        "TTS_TOO_SHORT",
    }
    duration_by_id = {item.beat_id: item.duration_ms for item in tts.beats}
    review_by_id = {item.beat_id: item for item in critic.beat_reviews}
    findings: list[AuditFinding] = []
    supported_ms = 0
    total_ms = sum(duration_by_id.values())
    for beat in storyboard.beats:
        review = review_by_id[beat.beat_id]
        evidence = set(beat.frame_evidence)
        has_evidence = bool(evidence) and bool(set(review.evidence_refs) & evidence)
        codes = set(review.finding_codes) | set(beat.finding_codes)
        if beat.status != "LOCKED":
            codes.add("BEAT_NOT_LOCKED")
        if not has_evidence:
            codes.add("MISSING_EVIDENCE")
        if not codes:
            supported_ms += duration_by_id[beat.beat_id]
        for code in sorted(codes):
            findings.append(
                AuditFinding(
                    "ERROR" if code in blocking_codes or code == "BEAT_NOT_LOCKED" else "WARNING",
                    code,
                    beat.beat_id,
                    review.note,
                    review.evidence_refs,
                )
            )

    coverage = Decimal(supported_ms) / Decimal(total_ms)
    if coverage < Decimal("0.90"):
        findings.append(
            AuditFinding(
                "ERROR",
                "DIRECT_EVIDENCE_BELOW_90",
                None,
                "Direct visual evidence coverage is below 0.90.",
                (),
            )
        )
    if expected_policy_sha256 != actual_policy_sha256:
        findings.append(
            AuditFinding(
                "ERROR",
                "POLICY_CHANGED_DURING_RUN",
                None,
                "Brain or validator policy changed during the episode run.",
                (),
            )
        )
    if not 420_000 <= render.duration_ms <= 720_000:
        findings.append(
            AuditFinding(
                "ERROR", "REVIEW_DURATION_OUT_OF_RANGE", None, "Final duration is invalid.", ()
            )
        )
    if render.video_stream_count != 1 or render.audio_stream_count != 1:
        findings.append(
            AuditFinding(
                "ERROR", "FINAL_STREAM_LAYOUT_INVALID", None, "Final stream layout is invalid.", ()
            )
        )
    if render.drift_ms > 80 or abs(total_ms - render.audio_duration_ms) > 80:
        findings.append(
            AuditFinding("ERROR", "AUDIO_VIDEO_DRIFT", None, "Final A/V drift exceeds 80 ms.", ())
        )
    passed = not any(item.severity == "ERROR" for item in findings)
    return EngineAuditReport(passed, _coverage_text(coverage), tuple(findings))
