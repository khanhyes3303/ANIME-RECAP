from __future__ import annotations

import subprocess
import wave
from pathlib import Path

from anime_review_mvp.adaptive_edl import AdaptiveEdlDocument, AdaptiveEdlSegment
from anime_review_mvp.models import EdlDocument, EdlSegment
from anime_review_mvp.render import probe_render, render_review


def _make_source(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def _make_narration(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=1",
            "-ar",
            "24000",
            "-ac",
            "1",
            str(path),
        ],
        check=True,
    )


def _dominant_zero_crossing_frequency(path: Path) -> float:
    with wave.open(str(path), "rb") as source:
        frames = source.readframes(source.getnframes())
        rate = source.getframerate()
        samples = [
            int.from_bytes(frames[index : index + 2], "little", signed=True)
            for index in range(0, len(frames), 2)
        ]
    crossings = sum(a <= 0 < b or a >= 0 > b for a, b in zip(samples, samples[1:], strict=False))
    return crossings * rate / (2 * len(samples))


def test_real_render_contains_narration_tone_not_source_tone(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    narration = tmp_path / "narration.wav"
    output = tmp_path / "review.mp4"
    extracted = tmp_path / "rendered.wav"
    _make_source(source)
    _make_narration(narration)
    edl = EdlDocument((EdlSegment("segment-001", "cue-001", 0, 1_000),))

    result = render_review(source, narration, edl, output, allow_short_fixture=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(output),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "24000",
            str(extracted),
        ],
        check=True,
    )

    assert result.video_stream_count == 1
    assert result.audio_stream_count == 1
    assert 950 < _dominant_zero_crossing_frequency(extracted) < 1_050
    assert probe_render(output, allow_short_fixture=True) == result


def test_real_adaptive_render_speeds_video_without_mapping_source_audio(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    narration = tmp_path / "narration.wav"
    output = tmp_path / "adaptive.mp4"
    _make_source(source)
    _make_narration(narration)
    edl = AdaptiveEdlDocument(
        (
            AdaptiveEdlSegment(
                "unit-001-segment-001",
                "unit-001",
                "situation-001",
                "range-001",
                0,
                1_250,
                0,
                1_000,
                1.25,
                ("shot-001",),
                ("event-001",),
            ),
        ),
        1_000,
    )

    result = render_review(source, narration, edl, output, allow_short_fixture=True)

    assert result.video_stream_count == 1
    assert result.audio_stream_count == 1
    assert result.drift_ms <= 80
