from __future__ import annotations

from dataclasses import replace

import pytest

from anime_review_mvp.audit import build_atomic_engine_audit
from anime_review_mvp.edl import build_atomic_edl
from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import (
    AtomicBeat,
    AtomicStoryboard,
    AtomicTtsBeat,
    AtomicTtsManifest,
    Claim,
    CriticBeatReview,
    CriticReviewDocument,
    FrameAnchor,
    FrameAnchorDocument,
    SpanSourceRange,
    TtsCacheStats,
)
from anime_review_mvp.render import RenderResult


def _board() -> AtomicStoryboard:
    claims = (
        Claim("claim-001", "ACTION", "Jiro runs.", ("event-001",)),
        Claim("claim-002", "REACTION", "Rago reacts.", ("event-002",)),
    )
    beats = (
        AtomicBeat(
            "beat-001",
            "scene-001",
            ("event-001",),
            ("claim-001",),
            (
                SpanSourceRange(
                    "range-001", 0, 336_000, "scene-001", "beat-001", ("shot-001",), ("event-001",)
                ),
            ),
            "Jiro chạy.",
            ("Jiro",),
            ("Jiro",),
            "ACTION",
            0,
            1_000,
            "Jiro lao đi.",
            ("frame-001.jpg",),
            336_000,
            336_000,
            "key-1",
            "LOCKED",
            (),
        ),
        AtomicBeat(
            "beat-002",
            "scene-002",
            ("event-002",),
            ("claim-002",),
            (
                SpanSourceRange(
                    "range-002",
                    336_000,
                    420_000,
                    "scene-002",
                    "beat-002",
                    ("shot-002",),
                    ("event-002",),
                ),
            ),
            "Rago quay lại.",
            ("Rago",),
            ("Rago",),
            "REACTION",
            336_000,
            337_000,
            "Rago quay phắt lại.",
            ("frame-002.jpg",),
            84_000,
            84_000,
            "key-2",
            "LOCKED",
            (),
        ),
    )
    return AtomicStoryboard("ANTIGRAVITY", "atomic-v1", "producer-01", claims, beats)


def _tts() -> AtomicTtsManifest:
    return AtomicTtsManifest(
        (
            AtomicTtsBeat("beat-001", "1.mp3", "1.wav", 336_000, "key-1"),
            AtomicTtsBeat("beat-002", "2.mp3", "2.wav", 84_000, "key-2"),
        ),
        "narration.wav",
        "fake",
        "BV074_streaming",
        "atomic-v1",
        TtsCacheStats(0, 2),
    )


def _anchors(timeline: str) -> FrameAnchorDocument:
    anchors = []
    for beat in _board().beats:
        for source_range in beat.source_ranges:
            suffix = "" if timeline == "SOURCE" else "-program"
            timestamps = (
                (
                    source_range.source_start_ms + 80,
                    (source_range.source_start_ms + source_range.source_end_ms) // 2,
                    source_range.source_end_ms - 80,
                )
                if timeline == "SOURCE"
                else (80, 1_000, 1_920)
            )
            anchors.extend(
                FrameAnchor(
                    f"{beat.beat_id}-{source_range.range_id}{suffix}-{position.casefold()}",
                    beat.beat_id,
                    source_range.range_id,
                    timeline,
                    position,
                    timestamp,
                    f"{beat.beat_id}-{timeline.casefold()}-{position.casefold()}.jpg",
                )
                for position, timestamp in zip(("START", "MIDDLE", "END"), timestamps, strict=True)
            )
    return FrameAnchorDocument(tuple(anchors))


def _evidence_for(beat_id: str) -> tuple[str, ...]:
    return tuple(
        anchor.anchor_id
        for anchor in (*_anchors("SOURCE").anchors, *_anchors("PROGRAM").anchors)
        if anchor.span_id == beat_id
    )


_COMPLETED_STAGES = (
    "LAP_STORYBOARD",
    "PHAN_BIEN_KICH_BAN",
    "TAO_TTS",
    "DUNG_PROXY",
    "PHAN_BIEN_VIDEO",
    "DUNG_VIDEO_CUOI",
)


def test_atomic_edl_rejects_action_window_outside_selected_footage() -> None:
    board = _board()
    bad = replace(board.beats[0], action_window_start_ms=500_000, action_window_end_ms=501_000)

    with pytest.raises(MvpError, match="action window"):
        build_atomic_edl(replace(board, beats=(bad, board.beats[1])), _tts())


def test_atomic_edl_preserves_many_shots_for_one_beat() -> None:
    board = _board()
    source_range = replace(board.beats[0].source_ranges[0], shot_ids=("shot-001", "shot-002"))
    first = replace(board.beats[0], source_ranges=(source_range,))

    edl = build_atomic_edl(replace(board, beats=(first, board.beats[1])), _tts())

    assert edl.segments[0].shot_ids == ("shot-001", "shot-002")
    assert edl.segments[-1].program_end_ms == 420_000


def test_atomic_audit_counts_only_evidenced_beats_without_blocking_findings() -> None:
    critic = CriticReviewDocument(
        "VIDEO",
        "producer-01",
        "critic-01",
        (
            CriticBeatReview(
                "beat-001",
                (),
                _evidence_for("beat-001"),
                "Jiro đang chạy trong cả source và program.",
                "Jiro chạy.",
                "MATCH",
                "Khớp hành động.",
            ),
            CriticBeatReview(
                "beat-002",
                ("VOICE_AHEAD",),
                _evidence_for("beat-002"),
                "Rago chỉ quay lại sau khi câu kể đã bắt đầu.",
                "Rago quay lại.",
                "VOICE_AHEAD",
                "Lời đi trước hình.",
            ),
        ),
    )
    render = RenderResult("proxy.mp4", 420_000, 420_000, 420_000, 0, 1, 1)

    report = build_atomic_engine_audit(
        _board(),
        _tts(),
        critic,
        _anchors("SOURCE"),
        _anchors("PROGRAM"),
        render,
        expected_policy_sha256="a" * 64,
        actual_policy_sha256="a" * 64,
        completed_stage_names=_COMPLETED_STAGES,
    )

    assert report.coverage_ratio == "0.8"
    assert report.passed is False
    assert {finding.code for finding in report.findings} >= {
        "VOICE_AHEAD",
        "DIRECT_EVIDENCE_BELOW_90",
    }


def test_atomic_audit_rejects_policy_change() -> None:
    critic = CriticReviewDocument(
        "VIDEO",
        "producer-01",
        "critic-01",
        tuple(
            CriticBeatReview(
                beat.beat_id,
                (),
                _evidence_for(beat.beat_id),
                f"Hình source và program của {beat.beat_id} cùng hành động.",
                beat.visual_fact,
                "MATCH",
                f"Đối chiếu {beat.beat_id} không thấy lệch.",
            )
            for beat in _board().beats
        ),
    )
    render = RenderResult("final.mp4", 420_000, 420_000, 420_000, 0, 1, 1)

    report = build_atomic_engine_audit(
        _board(),
        _tts(),
        critic,
        _anchors("SOURCE"),
        _anchors("PROGRAM"),
        render,
        expected_policy_sha256="a" * 64,
        actual_policy_sha256="b" * 64,
        completed_stage_names=_COMPLETED_STAGES,
    )

    assert "POLICY_CHANGED_DURING_RUN" in {finding.code for finding in report.findings}


def test_atomic_audit_rejects_missing_stage_metrics() -> None:
    critic = CriticReviewDocument(
        "VIDEO",
        "producer-01",
        "critic-01",
        tuple(
            CriticBeatReview(
                beat.beat_id,
                (),
                _evidence_for(beat.beat_id),
                f"Quan sát riêng {beat.beat_id}.",
                beat.visual_fact,
                "MATCH",
                f"Nhận xét riêng {beat.beat_id}.",
            )
            for beat in _board().beats
        ),
    )
    render = RenderResult("final.mp4", 420_000, 420_000, 420_000, 0, 1, 1)

    report = build_atomic_engine_audit(
        _board(),
        _tts(),
        critic,
        _anchors("SOURCE"),
        _anchors("PROGRAM"),
        render,
        expected_policy_sha256="a" * 64,
        actual_policy_sha256="a" * 64,
        completed_stage_names=(),
    )

    assert "MISSING_STAGE_METRICS" in {finding.code for finding in report.findings}
    assert report.passed is False
