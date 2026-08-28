from __future__ import annotations

import pytest

from anime_review_mvp.edl import build_edl_from_locked_spans
from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import (
    Claim,
    NarrationSpan,
    NarrationSpanDocument,
    SpanSourceRange,
    SpanTts,
    SpanTtsManifest,
)


def _document(
    *,
    start_ms: int = 1_000,
    end_ms: int = 3_000,
    short_action_exception: bool = False,
) -> NarrationSpanDocument:
    return NarrationSpanDocument(
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
                        "range-001",
                        start_ms,
                        end_ms,
                        "scene-001",
                        "beat-001",
                        ("shot-001",),
                        ("event-001",),
                        short_action_exception,
                    ),
                ),
            ),
        ),
        claims=(Claim("claim-001", "ACTION", "Jiro runs.", ("event-001",)),),
        owner="CODEX",
    )


def _tts(duration_ms: int) -> SpanTtsManifest:
    return SpanTtsManifest(
        spans=(SpanTts("span-001", "span-001.mp3", "span-001.wav", duration_ms),),
        narration_wav_path="narration.wav",
        provider="fake",
        voice_id="BV074_streaming",
    )


def test_edl_rejects_unapproved_micro_clip() -> None:
    with pytest.raises(MvpError, match="500 ms"):
        build_edl_from_locked_spans(_document(start_ms=1_000, end_ms=1_300), _tts(300))


def test_edl_accepts_explicit_short_action_exception() -> None:
    edl = build_edl_from_locked_spans(
        _document(start_ms=1_000, end_ms=1_300, short_action_exception=True),
        _tts(300),
    )

    assert edl.segments[0].short_action_exception is True
    assert edl.segments[0].program_end_ms == 300


def test_edl_never_trims_source_range_to_fit_tts() -> None:
    with pytest.raises(MvpError, match="differs from TTS"):
        build_edl_from_locked_spans(_document(), _tts(1_500))


def test_edl_preserves_exact_locked_range() -> None:
    edl = build_edl_from_locked_spans(_document(), _tts(2_000))

    assert (edl.segments[0].source_start_ms, edl.segments[0].source_end_ms) == (
        1_000,
        3_000,
    )
    assert edl.segments[0].span_id == "span-001"
