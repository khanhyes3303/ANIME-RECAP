from __future__ import annotations

from decimal import Decimal

from .errors import MvpError
from .models import (
    AuditFinding,
    CodexSemanticReview,
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
