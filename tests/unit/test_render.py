from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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
