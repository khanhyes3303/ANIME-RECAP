from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

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
        cue_gains_db=(1.25, -0.75),
    )
    graph = command[command.index("-filter_complex") + 1]
    assert "adelay=800|800" in graph
    assert "adelay=3400|3400" in graph
    assert "amix=inputs=3:duration=longest:normalize=0" in graph
    assert "atrim=duration=6.000" in graph
    assert "volume=1.250dB" in graph
    assert "volume=-0.750dB" in graph
    assert "alimiter=limit=0.794" in graph
    assert "anullsrc=r=48000:cl=mono" in command
    assert command[command.index("-ar") + 1] == "48000"


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


def test_render_levels_each_cue_to_common_mean_volume(tmp_path: Path) -> None:
    cue_paths = (tmp_path / "one.wav", tmp_path / "two.wav")
    for path in cue_paths:
        path.write_bytes(b"wav")
    output = tmp_path / "out.wav"
    measured = iter((-20.0, -16.0))
    graphs: list[str] = []

    def runner(command: list[str], **_: object) -> SimpleNamespace:
        if "volumedetect" in command:
            value = next(measured)
            return SimpleNamespace(returncode=0, stdout="", stderr=f"mean_volume: {value} dB")
        graphs.append(command[command.index("-filter_complex") + 1])
        output.write_bytes(b"aligned")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    render_cue_audio_timeline(
        _manifest(tuple(str(path) for path in cue_paths)),
        _timeline(),
        output,
        runner=runner,
    )

    assert "volume=2.000dB" in graphs[0]
    assert "volume=-2.000dB" in graphs[0]
