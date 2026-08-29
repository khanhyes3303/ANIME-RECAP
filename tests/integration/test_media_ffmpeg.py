from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from anime_review_mvp.gemini_packets import build_script_evidence_media
from anime_review_mvp.media import probe_source


def test_real_ffprobe_registers_one_video_and_one_audio_stream(tmp_path: Path) -> None:
    source = tmp_path / "fixture.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:duration=1",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
    )

    registered = probe_source(source)

    assert registered.duration_ms == 1_000
    assert registered.width == 320
    assert registered.height == 180
    assert registered.audio_stream_count == 1
    assert len(registered.sha256) == 64


def test_real_ffmpeg_builds_burned_in_script_evidence_video(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "script_evidence.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=640x360:d=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    source_range = SimpleNamespace(source_start_ms=0, source_end_ms=1_500)
    beat = SimpleNamespace(beat_id="beat-001", source_ranges=(source_range,))

    build_script_evidence_media(source, (beat,), output)

    assert output.is_file()
    assert output.stat().st_size > 1_000
