from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp.adaptive_edl import AdaptiveEdlDocument, AdaptiveEdlSegment
from anime_review_mvp.errors import MvpError
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.local_audit import (
    build_local_audit,
    content_fingerprint,
    load_semantic_review,
)
from anime_review_mvp.models import FrameAnchor, FrameAnchorDocument
from anime_review_mvp.render import RenderResult
from anime_review_mvp.situations import (
    EvidenceRange,
    NarrationPlan,
    NarrationUnit,
    SemanticReviewDocument,
    SemanticUnitReview,
    Situation,
    SituationDocument,
    SituationTts,
    SituationTtsManifest,
)


def _plan() -> NarrationPlan:
    evidence = EvidenceRange(
        "range-001",
        "situation-001",
        1_000,
        2_000,
        ("shot-001",),
        ("event-001",),
        ("transcript-001",),
        ("source-frame-001",),
        "Jiro phản công.",
    )
    return NarrationPlan(
        "LOCAL_EDITOR",
        "situation-v1",
        (
            NarrationUnit(
                "unit-001",
                "situation-001",
                ("Jiro phản công.",),
                "Jiro quay lại cho cả đám ăn hành.",
                "",
                "",
                (evidence,),
                "LOCKED",
            ),
        ),
    )


def _situations() -> SituationDocument:
    return SituationDocument(
        "LOCAL_EDITOR",
        "situation-v1",
        (
            Situation(
                "situation-001",
                1_000,
                3_000,
                "MAIN_PLOT",
                ("Jiro",),
                "Jiro bị tấn công.",
                ("Băng nhóm chủ động đánh Jiro.",),
                ("Jiro phản công.",),
                "Jiro thắng.",
                ("transcript-001",),
                ("source-frame-001",),
                None,
                None,
                1.0,
            ),
        ),
    )


def _anchors(timeline: str, anchor_id: str) -> FrameAnchorDocument:
    return FrameAnchorDocument(
        (
            FrameAnchor(
                anchor_id,
                "unit-001",
                "range-001",
                timeline,
                "MIDDLE",
                1_500 if timeline == "SOURCE" else 500,
                f"{anchor_id}.jpg",
            ),
        )
    )


def _review(*, supported: bool = True, unit_id: str = "unit-001") -> SemanticReviewDocument:
    return SemanticReviewDocument(
        "LOCAL_SEMANTIC_AUDITOR",
        (
            SemanticUnitReview(
                unit_id,
                supported,
                () if supported else ("UNSUPPORTED_STORY_CLAIM",),
                ("transcript-001",),
                ("source-anchor-001",),
                ("program-anchor-001",),
                "Khớp." if supported else "Không thấy kết quả được kể.",
            ),
        ),
    )


def _edl() -> AdaptiveEdlDocument:
    return AdaptiveEdlDocument(
        (
            AdaptiveEdlSegment(
                "segment-001",
                "unit-001",
                "situation-001",
                "range-001",
                1_000,
                2_000,
                0,
                1_000,
                1.0,
                ("shot-001",),
                ("event-001",),
            ),
        ),
        1_000,
    )


def _tts() -> SituationTtsManifest:
    unit = SituationTts("unit-001", "unit.mp3", "unit.wav", 1_000, "a" * 64)
    return SituationTtsManifest(
        (unit,), "narration.wav", "fake", "voice-001", "situation-v1", 0, 1, 1_000
    )


def _render() -> RenderResult:
    return RenderResult("review.mp4", 1_000, 1_000, 1_000, 0, 1, 1)


def test_semantic_review_cannot_omit_or_invent_units(tmp_path: Path) -> None:
    path = tmp_path / "semantic_review.json"
    dump_json(path, _review(unit_id="unit-invented"))

    with pytest.raises(MvpError, match="unit IDs must exactly match"):
        load_semantic_review(
            path,
            _plan(),
            _anchors("SOURCE", "source-anchor-001"),
            _anchors("PROGRAM", "program-anchor-001"),
        )


def test_local_audit_rejects_unsupported_story_claim() -> None:
    report = build_local_audit(
        _plan(),
        _situations(),
        _review(supported=False),
        _anchors("SOURCE", "source-anchor-001"),
        _anchors("PROGRAM", "program-anchor-001"),
        _edl(),
        _tts(),
        _render(),
    )

    assert report.passed is False
    assert "UNSUPPORTED_STORY_CLAIM" in {item.code for item in report.findings}


def test_local_audit_passes_only_when_semantic_and_technical_checks_pass() -> None:
    report = build_local_audit(
        _plan(),
        _situations(),
        _review(),
        _anchors("SOURCE", "source-anchor-001"),
        _anchors("PROGRAM", "program-anchor-001"),
        _edl(),
        _tts(),
        _render(),
    )

    assert report.passed is True
    assert report.coverage_ratio == "1"
    assert report.findings == ()


def test_content_fingerprint_changes_with_artifact_content(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    before = content_fingerprint((first, second))

    second.write_text("changed", encoding="utf-8")

    assert content_fingerprint((first, second)) != before
