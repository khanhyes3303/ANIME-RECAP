from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp.cue_audio import (
    build_cue_audio_command,
    render_cue_audio_timeline,
)
from anime_review_mvp.errors import MvpError
from anime_review_mvp.semantic_timeline import CueTiming, SemanticTimeline
from anime_review_mvp.situations import CueTts, CueTtsManifest


def _manifest(paths: tuple[str, ...]) -> CueTtsManifest:
    cues = tuple(
        CueTts(
            f"cue-{index:03d}",
            "unit-001",
            path,
            f"cue-{index:03d}.mp3",
            1_000,
            f"{index:x}" * 64,
        )
        for index, path in enumerate(paths, start=1)
    )
    return CueTtsManifest(cues, "fake", "voice", "situation-v2", 0, len(cues))


def _timeline() -> SemanticTimeline:
    return SemanticTimeline(
        (
            CueTiming("cue-001", 800, 1_800, 500),
            CueTiming("cue-002", 3_400, 4_400, 3_100),
        ),
        6_000,
    )


def test_cue_audio_command_places_each_wav_at_semantic_offset() -> None:
    command = build_cue_audio_command(
        _manifest(("cue-001.wav", "cue-002.wav")),
        _timeline(),
        Path("narration-aligned.wav"),
    )
    graph = command[command.index("-filter_complex") + 1]
    assert "adelay=800|800" in graph
    assert "adelay=3400|3400" in graph
    assert "amix=inputs=3:duration=longest" in graph
    assert "atrim=duration=6.000" in graph


def test_cue_audio_rejects_missing_wav(tmp_path: Path) -> None:
    with pytest.raises(MvpError, match="cue WAV does not exist"):
        render_cue_audio_timeline(
            _manifest((str(tmp_path / "missing-1.wav"), str(tmp_path / "missing-2.wav"))),
            _timeline(),
            tmp_path / "out.wav",
        )


def test_cue_audio_rejects_overlapping_timings() -> None:
    overlap = SemanticTimeline(
        (CueTiming("cue-001", 800, 1_800, 500), CueTiming("cue-002", 1_700, 2_700, 1_400)),
        3_000,
    )
    with pytest.raises(MvpError, match="overlap"):
        build_cue_audio_command(_manifest(("one.wav", "two.wav")), overlap, Path("out.wav"))
