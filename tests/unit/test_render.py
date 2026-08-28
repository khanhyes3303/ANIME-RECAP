from __future__ import annotations

from pathlib import Path

from anime_review_mvp.models import EdlDocument, EdlSegment
from anime_review_mvp.render import build_filter_graph, build_render_command


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
    assert "-shortest" in command
