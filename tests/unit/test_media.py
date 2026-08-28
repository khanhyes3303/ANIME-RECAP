from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.media import (
    detect_shots,
    extract_inspection_assets,
    probe_source,
    transcribe_english,
)
from anime_review_mvp.models import Shot


class FakeRunner:
    def __init__(self, *, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.result = SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> SimpleNamespace:
        self.commands.append(command)
        return self.result


class FakeWhisperModel:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.options: dict[str, object] = {}

    def transcribe(self, _: str, **options: object) -> dict[str, object]:
        self.options = options
        return self.payload


def test_probe_rejects_a_source_without_video_stream(tmp_path: Path) -> None:
    source = tmp_path / "audio-only.mp4"
    source.write_bytes(b"media")
    runner = FakeRunner(
        stdout=json.dumps({"format": {"duration": "10.0"}, "streams": []})
    )

    with pytest.raises(MvpError, match="exactly one video stream"):
        probe_source(source, runner=runner)


def test_transcribe_forces_english_and_persists_word_times(tmp_path: Path) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"media")
    model = FakeWhisperModel(
        {
            "language": "en",
            "segments": [
                {
                    "start": 1.0,
                    "end": 2.0,
                    "text": "Run!",
                    "words": [{"start": 1.0, "end": 1.5, "word": "Run"}],
                }
            ],
        }
    )
    output = tmp_path / "transcript.json"

    document = transcribe_english(source, output, model=model)

    assert document.language == "en"
    assert document.segments[0].start_ms == 1_000
    assert document.segments[0].words[0].end_ms == 1_500
    assert model.options == {
        "language": "en",
        "task": "transcribe",
        "word_timestamps": True,
        "verbose": False,
    }
    assert output.exists()


def test_detect_shots_adds_source_edges_around_ffmpeg_scene_cuts(tmp_path: Path) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"media")
    runner = FakeRunner(
        stderr="[Parsed_showinfo] n:1 pts:2500 pts_time:2.500 pos:0\n"
    )

    shots = detect_shots(source, 5_000, runner=runner)

    assert [(shot.start_ms, shot.end_ms) for shot in shots] == [(0, 2_500), (2_500, 5_000)]
    assert runner.commands[0][0] == "ffmpeg"


def test_extract_inspection_assets_writes_one_midpoint_frame_per_shot(
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"media")
    output_dir = tmp_path / "frames"
    runner = FakeRunner()
    shots = (
        Shot("shot-0001", 0, 2_000),
        Shot("shot-0002", 2_000, 5_000),
    )

    frames = extract_inspection_assets(source, shots, output_dir, runner=runner)

    assert frames == (
        output_dir / "shot-0001.jpg",
        output_dir / "shot-0002.jpg",
    )
    assert "1.000" in runner.commands[0]
    assert "3.500" in runner.commands[1]
