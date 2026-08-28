from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from anime_review_mvp.audit import build_engine_audit
from anime_review_mvp.errors import MvpError
from anime_review_mvp.jsonio import load_json
from anime_review_mvp.models import (
    Claim,
    CodexSemanticReview,
    FrameAnchor,
    FrameAnchorDocument,
    NarrationSpan,
    NarrationSpanDocument,
    SpanSemanticReview,
    SpanSourceRange,
    SpanTts,
    SpanTtsManifest,
)
from anime_review_mvp.render import RenderResult


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _review_payload() -> dict[str, object]:
    return {
        "owner": "CODEX",
        "spans": [
            {
                "span_id": "span-001",
                "supported": True,
                "finding_codes": [],
                "evidence_anchor_ids": [
                    "span-001-source-start",
                    "span-001-source-middle",
                    "span-001-source-end",
                    "span-001-program-start",
                    "span-001-program-middle",
                    "span-001-program-end",
                ],
                "note": "Hình và lời cùng thể hiện Jiro chạy qua cổng.",
            }
        ],
    }


def _documents() -> tuple[
    NarrationSpanDocument,
    SpanTtsManifest,
    FrameAnchorDocument,
    FrameAnchorDocument,
]:
    claims = (
        Claim("claim-001", "ACTION", "Jiro runs.", ("event-001",)),
        Claim("claim-002", "REACTION", "Rago reacts.", ("event-002",)),
    )
    spans = NarrationSpanDocument(
        spans=(
            NarrationSpan(
                "span-001",
                "Jiro lao qua cổng.",
                ("claim-001",),
                ("event-001",),
                ("Jiro",),
                "Jiro chạy qua cổng.",
                (
                    SpanSourceRange(
                        "range-001", 0, 336_000, "scene-001", "beat-001",
                        ("shot-001",), ("event-001",),
                    ),
                ),
            ),
            NarrationSpan(
                "span-002",
                "Rago ngoảnh lại.",
                ("claim-002",),
                ("event-002",),
                ("Rago",),
                "Rago ngoảnh lại.",
                (
                    SpanSourceRange(
                        "range-002", 336_000, 420_000, "scene-002", "beat-002",
                        ("shot-002",), ("event-002",),
                    ),
                ),
            ),
        ),
        claims=claims,
        owner="CODEX",
    )
    tts = SpanTtsManifest(
        spans=(
            SpanTts("span-001", "1.mp3", "1.wav", 336_000),
            SpanTts("span-002", "2.mp3", "2.wav", 84_000),
        ),
        narration_wav_path="narration.wav",
        provider="fake",
        voice_id="BV074_streaming",
    )

    def anchors(timeline: str) -> FrameAnchorDocument:
        items: list[FrameAnchor] = []
        for span_id in ("span-001", "span-002"):
            for position, timestamp in (("START", 1), ("MIDDLE", 2), ("END", 3)):
                items.append(
                    FrameAnchor(
                        f"{span_id}-{timeline.lower()}-{position.lower()}",
                        span_id,
                        f"range-{span_id[-1]}",
                        timeline,
                        position,
                        timestamp,
                        f"{span_id}-{timeline}-{position}.jpg",
                    )
                )
        return FrameAnchorDocument(tuple(items))

    return spans, tts, anchors("SOURCE"), anchors("PROGRAM")


def test_semantic_review_schema_has_no_passed_field(tmp_path: Path) -> None:
    payload = _review_payload()
    payload["passed"] = True

    with pytest.raises(MvpError, match="artifact contract"):
        load_json(_write(tmp_path / "codex_review.json", payload), CodexSemanticReview)


def test_engine_audit_rejects_non_codex_locked_spans() -> None:
    spans, tts, source_anchors, final_anchors = _documents()
    reviews = tuple(
        SpanSemanticReview(
            span.span_id,
            True,
            (),
            tuple(
                anchor.anchor_id
                for anchor in (*source_anchors.anchors, *final_anchors.anchors)
                if anchor.span_id == span.span_id
            ),
            "Khớp.",
        )
        for span in spans.spans
    )

    with pytest.raises(MvpError, match="locked narration owner must be CODEX"):
        build_engine_audit(
            replace(spans, owner="ANTIGRAVITY"),
            tts,
            CodexSemanticReview("CODEX", reviews),
            source_anchors,
            final_anchors,
            RenderResult("review.mp4", 420_000, 420_000, 420_000, 0, 1, 1),
        )


def test_engine_audit_weights_verified_spans_by_tts_duration() -> None:
    spans, tts, source_anchors, final_anchors = _documents()
    all_anchor_ids = tuple(
        anchor.anchor_id for anchor in (*source_anchors.anchors, *final_anchors.anchors)
    )
    review = CodexSemanticReview(
        "CODEX",
        (
            SpanSemanticReview(
                "span-001",
                True,
                (),
                tuple(item for item in all_anchor_ids if item.startswith("span-001")),
                "Khớp hình và lời.",
            ),
            SpanSemanticReview(
                "span-002",
                False,
                ("LOW_VALUE_FOOTAGE",),
                tuple(item for item in all_anchor_ids if item.startswith("span-002")),
                "Đoạn phụ không hỗ trợ trực tiếp nhưng không làm sai cốt truyện.",
            ),
        ),
    )
    render = RenderResult("review.mp4", 420_000, 420_000, 420_000, 0, 1, 1)

    report = build_engine_audit(
        spans, tts, review, source_anchors, final_anchors, render
    )

    assert report.coverage_ratio == "0.8"
    assert report.passed is True


def test_engine_audit_blocks_scene_mismatch_even_at_full_duration() -> None:
    spans, tts, source_anchors, final_anchors = _documents()
    reviews = []
    for span in spans.spans:
        evidence = tuple(
            anchor.anchor_id
            for anchor in (*source_anchors.anchors, *final_anchors.anchors)
            if anchor.span_id == span.span_id
        )
        reviews.append(
            SpanSemanticReview(
                span.span_id,
                True,
                ("SCENE_MISMATCH",) if span.span_id == "span-002" else (),
                evidence,
                "Sai cảnh." if span.span_id == "span-002" else "Khớp.",
            )
        )

    report = build_engine_audit(
        spans,
        tts,
        CodexSemanticReview("CODEX", tuple(reviews)),
        source_anchors,
        final_anchors,
        RenderResult("review.mp4", 420_000, 420_000, 420_000, 0, 1, 1),
    )

    assert report.passed is False
    assert "SCENE_MISMATCH" in {finding.code for finding in report.findings}
