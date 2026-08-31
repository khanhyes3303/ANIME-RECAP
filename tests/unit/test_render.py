from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from anime_review_mvp.adaptive_edl import AdaptiveEdlDocument, AdaptiveEdlSegment
from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import EdlDocument, EdlSegment
from anime_review_mvp.render import build_filter_graph, build_render_command, probe_render


def _edl() -> EdlDocument:
    return EdlDocument(
        (
            EdlSegment("segment-001", "cue-001", 0, 1_000),
            EdlSegment("segment-002", "cue-002", 2_000, 3_000),
        )
    )


def test_filter_graph_only_trims_resets_and_concats_video() -> None:
    graph = build_filter_graph(_edl())

    assert "trim=start=0.000:end=1.000" in graph
    assert "setpts=PTS-STARTPTS" in graph
    assert "concat=n=2:v=1:a=0" in graph
    for forbidden in ("atempo", "setpts=PTS/", "loop", "tpad", "freeze"):
        assert forbidden not in graph


def test_filter_graph_applies_adaptive_segment_playback_rate() -> None:
    edl = AdaptiveEdlDocument(
        segments=(
            AdaptiveEdlSegment(
                "unit-001-segment-001",
                "unit-001",
                "situation-001",
                "range-001",
                1_000,
                4_000,
                0,
                2_400,
                1.25,
                ("shot-001",),
                ("event-001",),
            ),
        ),
        total_duration_ms=2_400,
    )

    graph = build_filter_graph(edl)

    assert "setpts=(PTS-STARTPTS)/1.250000" in graph
    assert "trim=duration=2.400,setpts=PTS-STARTPTS" in graph


def test_adaptive_filter_graph_pads_frame_quantization_before_duration_trim() -> None:
    edl = AdaptiveEdlDocument(
        segments=(
            AdaptiveEdlSegment(
                "unit-001-segment-001",
                "unit-001",
                "situation-001",
                "range-001",
                1_000,
                4_000,
                0,
                2_400,
                1.0,
                ("shot-001",),
                ("event-001",),
            ),
        ),
        total_duration_ms=2_400,
    )

    graph = build_filter_graph(edl, quality="proxy")

    assert "tpad=stop_mode=clone:stop_duration=0.125" in graph
    assert graph.index("tpad=stop_mode=clone") < graph.index(
        "trim=duration=2.400"
    )


def test_ffmpeg_maps_only_rendered_video_and_tts_audio() -> None:
    command = build_render_command(
        Path("source.mp4"), Path("narration.wav"), _edl(), Path("out.mp4")
    )

    assert command.count("-map") == 2
    assert "1:a:0" in command
    assert "0:a" not in command
    assert "-shortest" not in command


def test_proxy_render_uses_360p_fast_preset_without_changing_timeline() -> None:
    command = build_render_command(
        Path("source.mp4"),
        Path("narration.wav"),
        _edl(),
        Path("proxy.mp4"),
        quality="proxy",
    )

    graph = command[command.index("-filter_complex") + 1]
    assert "scale=-2:360" in graph
    assert command[command.index("-preset") + 1] == "ultrafast"
    assert "trim=start=0.000:end=1.000" in graph


def test_probe_render_rejects_stream_drift_over_80_ms(tmp_path: Path) -> None:
    output = tmp_path / "review.mp4"
    output.write_bytes(b"media")
    payload = {
        "streams": [
            {"codec_type": "video", "duration": "8.000"},
            {"codec_type": "audio", "duration": "8.081"},
        ],
        "format": {"duration": "8.081"},
    }

    def runner(command: list[str], **_: object) -> SimpleNamespace:
        assert command[0] == "ffprobe"
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    with pytest.raises(MvpError, match="80 ms"):
        probe_render(output, allow_short_fixture=True, runner=runner)


def test_probe_render_accepts_adaptive_timeline_duration_without_fixed_bounds(
    tmp_path: Path,
) -> None:
    output = tmp_path / "review.mp4"
    output.write_bytes(b"media")
    payload = {
        "streams": [
            {"codec_type": "video", "duration": "808.3075"},
            {"codec_type": "audio", "duration": "808.2870"},
        ],
        "format": {"duration": "808.3075"},
    }

    def runner(command: list[str], **_: object) -> SimpleNamespace:
        assert command[0] == "ffprobe"
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    result = probe_render(output, duration_bounds_ms=None, runner=runner)

    assert result.duration_ms == 808_308
    assert result.drift_ms == 21
