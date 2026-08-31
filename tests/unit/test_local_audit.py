from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from anime_review_mvp.adaptive_edl import AdaptiveEdlDocument, AdaptiveEdlSegment
from anime_review_mvp.editor_provenance import AcceptedEditorialRevision
from anime_review_mvp.errors import MvpError
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.local_audit import (
    build_episode_coherence_audit,
    build_local_audit,
    build_v2_local_audit,
    content_fingerprint,
    load_semantic_review,
)
from anime_review_mvp.models import FrameAnchor, FrameAnchorDocument
from anime_review_mvp.render import RenderResult
from anime_review_mvp.semantic_timeline import CueTiming, SemanticTimeline
from anime_review_mvp.situations import (
    CueTts,
    CueTtsManifest,
    EvidenceRange,
    NarrationClaim,
    NarrationCue,
    NarrationPlan,
    NarrationUnit,
    SemanticReviewDocument,
    SemanticShotUse,
    SemanticUnitReview,
    Situation,
    SituationDocument,
    SituationTts,
    SituationTtsManifest,
    StoryContext,
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


def _v2_bundle() -> tuple[NarrationPlan, SituationDocument, CueTtsManifest, SemanticTimeline]:
    base_plan = _plan()
    use = SemanticShotUse("shot-001", "event-001", "ACTION", "Jiro phản công.")
    evidence = replace(
        base_plan.units[0].evidence_ranges[0],
        semantic_event_id="event-001",
        action_phase="ACTION",
        story_purpose="Jiro phản công.",
        shot_uses=(use,),
    )
    cue = NarrationCue(
        "cue-001",
        "situation-001",
        "Jiro phản công.",
        ("claim-001",),
        1_200,
        "ACTION",
        ("transcript-001",),
        ("source-frame-001",),
        ("shot-001",),
        ("Jiro",),
        ("Jiro",),
        (),
        (),
        300,
        300,
    )
    unit = replace(base_plan.units[0], evidence_ranges=(evidence,), cues=(cue,))
    plan = NarrationPlan(
        "LOCAL_EDITOR",
        "situation-v2",
        (unit,),
        (NarrationClaim("claim-001", "Jiro phản công.", ("event-001",)),),
    )
    situation = replace(
        _situations().situations[0],
        cause_or_goal="Jiro phải tự vệ.",
        audience_summary="Jiro bị đánh rồi phản công.",
    )
    situations = SituationDocument("LOCAL_EDITOR", "situation-v2", (situation,))
    tts = CueTtsManifest(
        (CueTts("cue-001", "unit-001", "cue.wav", "cue.mp3", 500, "b" * 64),),
        "fake",
        "voice",
        "situation-v2",
        0,
        1,
    )
    timeline = SemanticTimeline((CueTiming("cue-001", 1_500, 2_000, 1_200),), 2_000)
    return plan, situations, tts, timeline


def _provenance() -> tuple[AcceptedEditorialRevision, ...]:
    return (
        AcceptedEditorialRevision(
            "task-001",
            "run-001",
            "situation-001",
            1,
            "ANTIGRAVITY",
            "a" * 64,
            "b" * 64,
            "c" * 64,
        ),
    )


def test_v2_local_audit_requires_antigravity_provenance() -> None:
    plan, situations, tts, timeline = _v2_bundle()
    report = build_v2_local_audit(
        plan, situations, timeline, tts, _edl(), _render(), (), StoryContext((), (), (), "")
    )
    assert "EDITOR_PROVENANCE_INVALID" in {finding.code for finding in report.findings}


def test_v2_local_audit_fails_when_voice_precedes_visual_anchor() -> None:
    plan, situations, tts, _timeline = _v2_bundle()
    ahead = SemanticTimeline((CueTiming("cue-001", 1_000, 1_500, 6_000),), 6_000)
    report = build_v2_local_audit(
        plan,
        situations,
        ahead,
        tts,
        _edl(),
        replace(_render(), duration_ms=6_000, video_duration_ms=6_000, audio_duration_ms=6_000),
        _provenance(),
        StoryContext((), (), (), ""),
    )
    assert "VOICE_PRECEDES_VISUAL_ANCHOR" in {finding.code for finding in report.findings}


def test_v2_local_audit_rejects_production_duration_under_seven_minutes() -> None:
    plan, situations, tts, timeline = _v2_bundle()
    report = build_v2_local_audit(
        plan,
        situations,
        timeline,
        tts,
        _edl(),
        _render(),
        _provenance(),
        StoryContext((), (), (), ""),
    )

    assert "PRODUCTION_DURATION_OUT_OF_RANGE" in {finding.code for finding in report.findings}


def test_episode_audit_rejects_unintroduced_character() -> None:
    plan, situations, _tts_manifest, _timeline = _v2_bundle()
    cue = replace(plan.units[0].cues[0], introduces_characters=(), mentions_characters=("Rago",))
    plan = replace(plan, units=(replace(plan.units[0], cues=(cue,)),))
    report = build_episode_coherence_audit(plan, situations, StoryContext((), (), (), ""))
    assert "CHARACTER_USED_BEFORE_INTRODUCTION" in {finding.code for finding in report.findings}
