from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from anime_review_mvp.adaptive_edl import AdaptiveEdlDocument, AdaptiveEdlSegment
from anime_review_mvp.errors import MvpError
from anime_review_mvp.media import (
    build_contact_sheets,
    detect_shots,
    extract_adaptive_program_anchors,
    extract_atomic_source_anchors,
    extract_dense_beat_evidence,
    extract_inspection_assets,
    extract_program_anchors,
    extract_span_anchors,
    probe_source,
    transcribe_english,
)
from anime_review_mvp.models import (
    AtomicBeat,
    AtomicStoryboard,
    Claim,
    DenseEvidenceDocument,
    DenseFrame,
    NarrationSpan,
    NarrationSpanDocument,
    Shot,
    SpanEdlDocument,
    SpanEdlSegment,
    SpanSourceRange,
)


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
    runner = FakeRunner(stdout=json.dumps({"format": {"duration": "10.0"}, "streams": []}))

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
    runner = FakeRunner(stderr="[Parsed_showinfo] n:1 pts:2500 pts_time:2.500 pos:0\n")

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


def test_extract_span_anchors_requests_start_middle_and_end(tmp_path: Path) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"media")
    output_dir = tmp_path / "anchors"
    runner = FakeRunner()
    document = NarrationSpanDocument(
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
                        1_000,
                        4_000,
                        "scene-001",
                        "beat-001",
                        ("shot-0001",),
                        ("event-001",),
                    ),
                ),
            ),
        ),
        claims=(Claim("claim-001", "ACTION", "Jiro runs.", ("event-001",)),),
        owner="CODEX",
    )

    anchors = extract_span_anchors(
        source,
        document,
        output_dir,
        timeline="SOURCE",
        runner=runner,
    )

    assert [anchor.position for anchor in anchors.anchors] == ["START", "MIDDLE", "END"]
    assert [anchor.timestamp_ms for anchor in anchors.anchors] == [1_080, 2_500, 3_920]
    assert all(anchor.timeline == "SOURCE" for anchor in anchors.anchors)
    assert [command[command.index("-ss") + 1] for command in runner.commands] == [
        "1.080",
        "2.500",
        "3.920",
    ]
    assert (output_dir / "anchors.json").is_file()


def test_extract_atomic_source_anchors_uses_each_beat_range(tmp_path: Path) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"media")
    output_dir = tmp_path / "atomic-source"
    runner = FakeRunner()
    source_range = SpanSourceRange(
        "range-001",
        1_000,
        4_000,
        "scene-001",
        "beat-001",
        ("shot-001",),
        ("event-001",),
    )
    board = AtomicStoryboard(
        "ANTIGRAVITY",
        "atomic-v2",
        "producer-01",
        (Claim("claim-001", "ACTION", "Jiro runs.", ("event-001",)),),
        (
            AtomicBeat(
                "beat-001",
                "scene-001",
                ("event-001",),
                ("claim-001",),
                (source_range,),
                "Jiro chạy qua cổng.",
                ("Jiro",),
                ("Jiro",),
                "ACTION",
                1_080,
                2_700,
                "Jiro lao qua cổng.",
                ("shot-001.jpg",),
                3_000,
                None,
                "",
                "LOCKED",
                (),
            ),
        ),
    )

    anchors = extract_atomic_source_anchors(source, board, output_dir, runner=runner)

    assert [anchor.position for anchor in anchors.anchors] == ["START", "MIDDLE", "END"]
    assert all(anchor.span_id == "beat-001" for anchor in anchors.anchors)
    assert all(anchor.timeline == "SOURCE" for anchor in anchors.anchors)
    assert (output_dir / "anchors.json").is_file()


def test_dense_evidence_covers_boundaries_and_action_window(tmp_path: Path) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"media")
    source_range = SpanSourceRange(
        "range-001", 1_000, 4_000, "scene-001", "beat-001", ("shot-001",), ("event-001",)
    )
    board = AtomicStoryboard(
        "ANTIGRAVITY",
        "atomic-v2",
        "producer-01",
        (Claim("claim-001", "ACTION", "Jiro runs.", ("event-001",)),),
        (
            AtomicBeat(
                "beat-001", "scene-001", ("event-001",), ("claim-001",), (source_range,),
                "Jiro chạy qua cổng.", ("Jiro",), ("Jiro",), "ACTION", 1_500, 2_700,
                "Jiro lao qua cổng.", ("shot-001.jpg",), 3_000, None, "", "LOCKED", (),
            ),
        ),
    )

    class WritingRunner(FakeRunner):
        def __call__(self, command: list[str], **kwargs: object) -> SimpleNamespace:
            result = super().__call__(command, **kwargs)
            output = Path(command[-1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"frame")
            return result

    evidence = extract_dense_beat_evidence(
        source, board, None, tmp_path / "dense", "SOURCE", runner=WritingRunner()
    )
    stamps = [frame.timestamp_ms for frame in evidence.frames if frame.beat_id == "beat-001"]

    assert {1_000, 1_500, 2_700, 4_000} <= set(stamps)
    assert max(b - a for a, b in zip(stamps, stamps[1:], strict=False)) <= 1_000
    assert (tmp_path / "dense" / "manifest.json").is_file()


def test_dense_program_evidence_uses_edl_timestamps(tmp_path: Path) -> None:
    video = tmp_path / "candidate.mp4"
    video.write_bytes(b"media")
    edl = SpanEdlDocument(
        (
            SpanEdlSegment(
                "segment-001", "beat-001", 1_000, 4_000, 2_000, 5_000,
                "range-001", "scene-001", "beat-001", ("shot-001",), ("event-001",), False,
            ),
        )
    )

    class WritingRunner(FakeRunner):
        def __call__(self, command: list[str], **kwargs: object) -> SimpleNamespace:
            result = super().__call__(command, **kwargs)
            output = Path(command[-1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"frame")
            return result

    evidence = extract_dense_beat_evidence(
        video, None, edl, tmp_path / "program-dense", "PROGRAM", runner=WritingRunner()
    )
    stamps = [frame.timestamp_ms for frame in evidence.frames]
    assert stamps[0] == 2_000
    assert stamps[-1] == 5_000


def test_contact_sheets_paginate_each_beat_at_twelve_frames(tmp_path: Path) -> None:
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"media")
    frames = tuple(
        DenseFrame(
            f"frame-{index:02d}", "beat-001", "range-001", "SOURCE", index * 100,
            str(tmp_path / f"frame-{index:02d}.jpg"), "a" * 64,
        )
        for index in range(13)
    )
    for frame in frames:
        Path(frame.path).write_bytes(b"frame")
    evidence = DenseEvidenceDocument("SOURCE", frames)

    class WritingRunner(FakeRunner):
        def __call__(self, command: list[str], **kwargs: object) -> SimpleNamespace:
            result = super().__call__(command, **kwargs)
            Path(command[-1]).write_bytes(b"sheet")
            return result

    runner = WritingRunner()
    sheets = build_contact_sheets(evidence, tmp_path / "sheets", runner=runner)

    assert len(sheets.sheets) == 2
    assert [len(sheet.frame_ids) for sheet in sheets.sheets] == [12, 1]
    assert any("drawtext" in argument for argument in runner.commands[0])
    assert (tmp_path / "sheets" / "manifest.json").is_file()


def test_extract_program_anchors_uses_edl_program_timing(tmp_path: Path) -> None:
    video = tmp_path / "candidate.mp4"
    video.write_bytes(b"media")
    runner = FakeRunner()
    edl = SpanEdlDocument(
        (
            SpanEdlSegment(
                "segment-001",
                "span-001",
                10_000,
                12_000,
                2_000,
                4_000,
                "range-001",
                "scene-001",
                "beat-001",
                ("shot-001",),
                ("event-001",),
                False,
            ),
        )
    )

    anchors = extract_program_anchors(video, edl, tmp_path / "program", runner=runner)

    assert [anchor.timestamp_ms for anchor in anchors.anchors] == [2_080, 3_000, 3_920]
    assert all(anchor.timeline == "PROGRAM" for anchor in anchors.anchors)


def test_extract_adaptive_program_anchors_uses_unit_ids(tmp_path: Path) -> None:
    video = tmp_path / "candidate.mp4"
    video.write_bytes(b"media")
    runner = FakeRunner()
    edl = AdaptiveEdlDocument(
        (
            AdaptiveEdlSegment(
                "segment-001",
                "unit-001",
                "situation-001",
                "range-001",
                10_000,
                12_000,
                2_000,
                4_000,
                1.0,
                ("shot-001",),
                ("event-001",),
            ),
        ),
        4_000,
    )

    anchors = extract_adaptive_program_anchors(
        video, edl, tmp_path / "program", runner=runner
    )

    assert {anchor.span_id for anchor in anchors.anchors} == {"unit-001"}
    assert [anchor.timestamp_ms for anchor in anchors.anchors] == [2_080, 3_000, 3_920]


def test_extract_program_anchors_allows_nonstandard_jpeg_pixel_format(
    tmp_path: Path,
) -> None:
    video = tmp_path / "candidate.mp4"
    video.write_bytes(b"media")
    runner = FakeRunner()
    edl = SpanEdlDocument(
        (
            SpanEdlSegment(
                "segment-001",
                "span-001",
                10_000,
                12_000,
                2_000,
                4_000,
                "range-001",
                "scene-001",
                "beat-001",
                ("shot-001",),
                ("event-001",),
                False,
            ),
        )
    )

    extract_program_anchors(video, edl, tmp_path / "program", runner=runner)

    jpeg_commands = [command for command in runner.commands if "-frames:v" in command]
    assert jpeg_commands
    assert any(
        command[command.index("-strict") + 1] == "-2"
        for command in jpeg_commands
        if "-strict" in command
    )
