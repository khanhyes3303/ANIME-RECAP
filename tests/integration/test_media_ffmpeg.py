from __future__ import annotations

import subprocess
from pathlib import Path

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
