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
            CriticBeatReview("beat-001", (), ("frame-001.jpg",), "Khớp."),
            CriticBeatReview(
                "beat-002", ("VOICE_AHEAD",), ("frame-002.jpg",), "Lời đi trước hình."
            ),
        ),
    )
    render = RenderResult("proxy.mp4", 420_000, 420_000, 420_000, 0, 1, 1)

    report = build_atomic_engine_audit(
        _board(),
        _tts(),
        critic,
        render,
        expected_policy_sha256="a" * 64,
        actual_policy_sha256="a" * 64,
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
            CriticBeatReview(beat.beat_id, (), beat.frame_evidence, "Khớp.")
            for beat in _board().beats
        ),
    )
    render = RenderResult("final.mp4", 420_000, 420_000, 420_000, 0, 1, 1)

    report = build_atomic_engine_audit(
        _board(),
        _tts(),
        critic,
        render,
        expected_policy_sha256="a" * 64,
        actual_policy_sha256="b" * 64,
    )

    assert "POLICY_CHANGED_DURING_RUN" in {finding.code for finding in report.findings}
