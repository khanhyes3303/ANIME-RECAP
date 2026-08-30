from __future__ import annotations

import json
from pathlib import Path

import pytest

from anime_review_mvp.adaptive_edl import build_adaptive_edl
from anime_review_mvp.local_audit import build_local_audit
from anime_review_mvp.models import Event, FrameAnchor, FrameAnchorDocument, Shot, TruthDocument
from anime_review_mvp.render import RenderResult
from anime_review_mvp.situation_validation import (
    validate_narration_plan,
    validate_situations,
)
from anime_review_mvp.situations import (
    EditorialPolicy,
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

FIXTURES = Path(__file__).parents[1] / "fixtures"


@pytest.mark.parametrize("fixture_name", ("situation_dialogue", "situation_action"))
def test_same_engine_handles_dialogue_and_action(fixture_name: str) -> None:
    case = json.loads((FIXTURES / fixture_name / "case.json").read_text(encoding="utf-8"))
    ranges = case["ranges"]
    policy = EditorialPolicy(forbidden_before_ms=case["forbidden_before_ms"])
    shots = tuple(
        Shot(f"shot-{index:03d}", item["start_ms"], item["end_ms"])
        for index, item in enumerate(ranges, start=1)
    )
    events = tuple(
        Event(
            f"event-{index:03d}",
            item["start_ms"],
            item["end_ms"],
            ("Hero",),
            item["fact"],
            "MAIN",
            1.0,
        )
        for index, item in enumerate(ranges, start=1)
    )
    truth = TruthDocument(events, (), True)
    situations = SituationDocument(
        "LOCAL_EDITOR",
        "situation-v1",
        tuple(
            Situation(
                f"situation-{index:03d}",
                item["start_ms"],
                item["end_ms"],
                "MAIN_PLOT",
                ("Hero",),
                item["fact"],
                (item["fact"],),
                (item["fact"],),
                item["fact"],
                (f"transcript-{index:03d}",),
                (f"source-frame-{index:03d}",),
                f"situation-{index - 1:03d}" if index > 1 else None,
                f"situation-{index + 1:03d}" if index < len(ranges) else None,
                1.0,
            )
            for index, item in enumerate(ranges, start=1)
        ),
    )
    plan = NarrationPlan(
        "LOCAL_EDITOR",
        "situation-v1",
        tuple(
            NarrationUnit(
                f"unit-{index:03d}",
                f"situation-{index:03d}",
                (item["fact"],),
                f"Nói gọn nè: {item['fact']}",
                "Nối từ tình huống trước." if index > 1 else "",
                "Chuyện chưa dừng ở đó." if index < len(ranges) else "",
                (
                    EvidenceRange(
                        f"range-{index:03d}",
                        f"situation-{index:03d}",
                        item["start_ms"],
                        item["end_ms"],
                        (f"shot-{index:03d}",),
                        (f"event-{index:03d}",),
                        (f"transcript-{index:03d}",),
                        (f"source-frame-{index:03d}",),
                        item["fact"],
                    ),
                ),
                "LOCKED",
            )
            for index, item in enumerate(ranges, start=1)
        ),
    )
    tts = SituationTtsManifest(
        tuple(
            SituationTts(
                f"unit-{index:03d}",
                f"unit-{index:03d}.mp3",
                f"unit-{index:03d}.wav",
                item["voice_ms"],
                f"{index:x}" * 64,
            )
            for index, item in enumerate(ranges, start=1)
        ),
        "narration.wav",
        "fixture",
        "voice-001",
        "situation-v1",
        0,
        len(ranges),
        sum(item["voice_ms"] for item in ranges),
    )

    validate_situations(
        situations,
        truth,
        shots,
        source_duration_ms=case["source_duration_ms"],
    )
    validate_narration_plan(
        plan,
        situations,
        truth,
        shots,
        policy,
        case["source_duration_ms"],
    )
    edl = build_adaptive_edl(
        plan,
        tts,
        source_duration_ms=case["source_duration_ms"],
        policy=policy,
    )
    source_anchors = FrameAnchorDocument(
        tuple(
            FrameAnchor(
                f"source-anchor-{index:03d}",
                f"unit-{index:03d}",
                f"range-{index:03d}",
                "SOURCE",
                "MIDDLE",
                (item["start_ms"] + item["end_ms"]) // 2,
                f"source-{index:03d}.jpg",
            )
            for index, item in enumerate(ranges, start=1)
        )
    )
    program_anchors = FrameAnchorDocument(
        tuple(
            FrameAnchor(
                f"program-anchor-{index:03d}",
                f"unit-{index:03d}",
                f"range-{index:03d}",
                "PROGRAM",
                "MIDDLE",
                segment.program_start_ms
                + (segment.program_end_ms - segment.program_start_ms) // 2,
                f"program-{index:03d}.jpg",
            )
            for index, (_item, segment) in enumerate(
                zip(ranges, edl.segments, strict=True), start=1
            )
        )
    )
    semantic = SemanticReviewDocument(
        "LOCAL_SEMANTIC_AUDITOR",
        tuple(
            SemanticUnitReview(
                f"unit-{index:03d}",
                True,
                (),
                (f"transcript-{index:03d}",),
                (f"source-anchor-{index:03d}",),
                (f"program-anchor-{index:03d}",),
                "Khớp thông tin cốt truyện.",
            )
            for index, _item in enumerate(ranges, start=1)
        ),
    )
    render = RenderResult(
        "review.mp4",
        edl.total_duration_ms,
        edl.total_duration_ms,
        edl.total_duration_ms,
        0,
        1,
        1,
    )
    audit = build_local_audit(
        plan,
        situations,
        semantic,
        source_anchors,
        program_anchors,
        edl,
        tts,
        render,
        policy=policy,
    )
    omitted_gaps = tuple(
        ranges[index + 1]["start_ms"] - ranges[index]["end_ms"]
        for index in range(len(ranges) - 1)
    ) + (case["source_duration_ms"] - ranges[-1]["end_ms"],)

    assert audit.passed is True
    assert len(omitted_gaps) == 3
    assert all(gap >= 500 for gap in omitted_gaps)
    assert all(0.8 <= segment.playback_rate <= 1.3 for segment in edl.segments)
