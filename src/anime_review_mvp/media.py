from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .errors import MvpError
from .jsonio import dump_json
from .models import (
    AtomicStoryboard,
    ContactSheet,
    ContactSheetDocument,
    DenseEvidenceDocument,
    DenseFrame,
    FrameAnchor,
    FrameAnchorDocument,
    NarrationSpanDocument,
    Shot,
    SourceRef,
    SpanEdlDocument,
    TranscriptDocument,
    TranscriptSegment,
    TranscriptWord,
)

Runner = Callable[..., Any]
_PTS_TIME = re.compile(r"pts_time:([0-9]+(?:\.[0-9]+)?)")


def extract_atomic_source_anchors(
    video: Path,
    storyboard: AtomicStoryboard,
    output_dir: Path,
    *,
    runner: Runner = subprocess.run,
) -> FrameAnchorDocument:
    if not video.is_file():
        raise MvpError(f"anchor video does not exist: {video}")
    output_dir.mkdir(parents=True, exist_ok=True)
    anchors: list[FrameAnchor] = []
    for beat in storyboard.beats:
        for source_range in beat.source_ranges:
            for position, timestamp_ms in zip(
                ("START", "MIDDLE", "END"),
                _anchor_timestamps(source_range.source_start_ms, source_range.source_end_ms),
                strict=True,
            ):
                anchor_id = f"{beat.beat_id}-{source_range.range_id}-{position.casefold()}"
                frame = output_dir / f"{anchor_id}.jpg"
                _run(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-ss",
                        f"{timestamp_ms / 1_000:.3f}",
                        "-i",
                        str(video),
                        "-frames:v",
                        "1",
                        "-strict",
                        "-2",
                        str(frame),
                    ],
                    runner,
                )
                anchors.append(
                    FrameAnchor(
                        anchor_id,
                        beat.beat_id,
                        source_range.range_id,
                        "SOURCE",
                        position,
                        timestamp_ms,
                        str(frame.resolve()),
                    )
                )
    result = FrameAnchorDocument(tuple(anchors))
    dump_json(output_dir / "anchors.json", result)
    return result


def extract_dense_beat_evidence(
    video: Path,
    storyboard: AtomicStoryboard | None,
    edl: SpanEdlDocument | None,
    output_dir: Path,
    timeline: str,
    *,
    max_gap_ms: int = 1_000,
    runner: Runner = subprocess.run,
) -> DenseEvidenceDocument:
    if not video.is_file():
        raise MvpError(f"dense evidence video does not exist: {video}")
    if timeline not in {"SOURCE", "PROGRAM"}:
        raise MvpError("dense evidence timeline is invalid")
    if max_gap_ms <= 0:
        raise MvpError("dense evidence max gap must be positive")
    if timeline == "SOURCE" and storyboard is None:
        raise MvpError("SOURCE dense evidence requires an atomic storyboard")
    if timeline == "PROGRAM" and edl is None:
        raise MvpError("PROGRAM dense evidence requires an EDL")

    ranges: list[tuple[str, str, int, int, tuple[int, ...]]] = []
    if timeline == "SOURCE":
        assert storyboard is not None
        for beat in storyboard.beats:
            action_points = tuple(
                point
                for point in (beat.action_window_start_ms, beat.action_window_end_ms)
                if point is not None
            )
            for source_range in beat.source_ranges:
                ranges.append(
                    (
                        beat.beat_id,
                        source_range.range_id,
                        source_range.source_start_ms,
                        source_range.source_end_ms,
                        action_points,
                    )
                )
    else:
        assert edl is not None
        for segment in edl.segments:
            ranges.append(
                (
                    segment.beat_id or segment.span_id,
                    segment.range_id,
                    segment.program_start_ms,
                    segment.program_end_ms,
                    (),
                )
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[DenseFrame] = []
    for beat_id, range_id, start_ms, end_ms, action_points in ranges:
        timestamps = _dense_timestamps(start_ms, end_ms, action_points, max_gap_ms)
        for timestamp_ms in timestamps:
            frame_id = f"{beat_id}-{range_id}-{timeline.casefold()}-{timestamp_ms:08d}"
            frame = output_dir / f"{frame_id}.jpg"
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-ss",
                    f"{timestamp_ms / 1_000:.3f}",
                    "-i",
                    str(video),
                    "-frames:v",
                    "1",
                    "-q:v",
                    "2",
                    str(frame),
                ],
                runner,
            )
            if not frame.is_file():
                raise MvpError(f"FFmpeg did not create dense evidence frame: {frame}")
            frames.append(
                DenseFrame(
                    frame_id,
                    beat_id,
                    range_id,
                    timeline,
                    timestamp_ms,
                    str(frame.resolve()),
                    hashlib.sha256(frame.read_bytes()).hexdigest(),
                )
            )
    if not frames:
        raise MvpError("dense evidence requires at least one source range")
    result = DenseEvidenceDocument(timeline, tuple(frames))
    dump_json(output_dir / "manifest.json", result)
    return result


def build_contact_sheets(
    evidence: DenseEvidenceDocument,
    output_dir: Path,
    *,
    max_frames: int = 12,
    runner: Runner = subprocess.run,
) -> ContactSheetDocument:
    if max_frames <= 0:
        raise MvpError("contact sheet max frames must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[DenseFrame]] = {}
    for frame in evidence.frames:
        grouped.setdefault(frame.beat_id, []).append(frame)
    sheets: list[ContactSheet] = []
    for beat_id, beat_frames in grouped.items():
        for index in range(0, len(beat_frames), max_frames):
            chunk = beat_frames[index : index + max_frames]
            sheet_id = f"{beat_id}-{evidence.timeline.casefold()}-{index // max_frames + 1:03d}"
            sheet = output_dir / f"{sheet_id}.jpg"
            concat_list = output_dir / f".{sheet_id}.concat.txt"
            concat_contents = "".join(
                f"file '{frame.path.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n"
                for frame in chunk
            )
            concat_list.write_text(
                concat_contents,
                encoding="utf-8",
            )
            try:
                label = (
                    f"{beat_id} | {evidence.timeline} | "
                    f"{chunk[0].timestamp_ms}ms-{chunk[-1].timestamp_ms}ms"
                )
                escaped_label = (
                    label.replace("\\", "\\\\")
                    .replace(":", "\\:")
                    .replace("'", "\\'")
                )
                _run(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        str(concat_list),
                        "-vf",
                        "scale=320:-2,tile=4x3:padding=8:margin=8,"
                        f"drawtext=text='{escaped_label}':x=8:y=8:fontsize=18:"
                        "fontcolor=white:box=1:boxcolor=black@0.6",
                        "-frames:v",
                        "1",
                        "-q:v",
                        "2",
                        str(sheet),
                    ],
                    runner,
                )
            finally:
                concat_list.unlink(missing_ok=True)
            if not sheet.is_file():
                raise MvpError(f"FFmpeg did not create contact sheet: {sheet}")
            sheets.append(
                ContactSheet(
                    sheet_id,
                    evidence.timeline,
                    beat_id,
                    tuple(frame.frame_id for frame in chunk),
                    str(sheet.resolve()),
                    hashlib.sha256(sheet.read_bytes()).hexdigest(),
                )
            )
    result = ContactSheetDocument(tuple(sheets))
    dump_json(output_dir / "manifest.json", result)
    return result


def _dense_timestamps(
    start_ms: int,
    end_ms: int,
    action_points: tuple[int, ...],
    max_gap_ms: int,
) -> tuple[int, ...]:
    if start_ms < 0 or end_ms <= start_ms:
        raise MvpError("dense evidence range is invalid")
    points = {start_ms, end_ms}
    points.update(point for point in action_points if start_ms <= point <= end_ms)
    current = start_ms
    while current + max_gap_ms < end_ms:
        current += max_gap_ms
        points.add(current)
    return tuple(sorted(points))


def _run(command: list[str], runner: Runner) -> Any:
    result = runner(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "unknown media-tool error").strip()
        raise MvpError(f"media command failed: {message}")
    return result


def probe_source(video: Path, *, runner: Runner = subprocess.run) -> SourceRef:
    if not video.is_file():
        raise MvpError(f"source video does not exist: {video}")
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(video),
        ],
        runner,
    )
    try:
        payload = json.loads(result.stdout)
        streams = payload["streams"]
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if len(video_streams) != 1:
            raise MvpError("source must contain exactly one video stream")
        stream = video_streams[0]
        duration_seconds = float(payload["format"]["duration"])
        duration_ms = round(duration_seconds * 1_000)
        if duration_ms <= 0:
            raise MvpError("source duration must be positive")
        width = int(stream["width"])
        height = int(stream["height"])
        time_base = str(stream.get("time_base", "unknown"))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MvpError("ffprobe returned an invalid source description") from exc

    digest = hashlib.sha256()
    with video.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return SourceRef(
        path=str(video.resolve()),
        sha256=digest.hexdigest(),
        duration_ms=duration_ms,
        width=width,
        height=height,
        time_base=time_base,
        audio_stream_count=len(audio_streams),
    )


def _milliseconds(value: object) -> int:
    try:
        return round(float(value) * 1_000)
    except (TypeError, ValueError) as exc:
        raise MvpError("Whisper returned an invalid timestamp") from exc


def transcribe_english(
    video: Path,
    output: Path,
    *,
    model: Any = None,
    model_name: str = "small",
) -> TranscriptDocument:
    if not video.is_file():
        raise MvpError(f"source video does not exist: {video}")
    if model is None:
        import whisper

        model = whisper.load_model(model_name)
    raw = model.transcribe(
        str(video),
        language="en",
        task="transcribe",
        word_timestamps=True,
        verbose=False,
    )
    if raw.get("language") != "en":
        raise MvpError("English dub transcription did not resolve as English")

    segments = tuple(
        TranscriptSegment(
            start_ms=_milliseconds(segment["start"]),
            end_ms=_milliseconds(segment["end"]),
            text=str(segment.get("text", "")).strip(),
            words=tuple(
                TranscriptWord(
                    start_ms=_milliseconds(word["start"]),
                    end_ms=_milliseconds(word["end"]),
                    text=str(word.get("word", "")).strip(),
                )
                for word in segment.get("words", ())
            ),
        )
        for segment in raw.get("segments", ())
    )
    document = TranscriptDocument(language="en", segments=segments)
    dump_json(output, document)
    return document


def detect_shots(
    video: Path,
    duration_ms: int,
    *,
    runner: Runner = subprocess.run,
) -> tuple[Shot, ...]:
    if duration_ms <= 0:
        raise MvpError("source duration must be positive")
    result = _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(video),
            "-vf",
            "select=gt(scene\\,0.30),showinfo",
            "-an",
            "-f",
            "null",
            "-",
        ],
        runner,
    )
    boundaries = {0, duration_ms}
    boundaries.update(
        round(float(match) * 1_000)
        for match in _PTS_TIME.findall(result.stderr or "")
        if 0 < float(match) * 1_000 < duration_ms
    )
    ordered = sorted(boundaries)
    return tuple(
        Shot(f"shot-{index:04d}", start, end)
        for index, (start, end) in enumerate(zip(ordered, ordered[1:], strict=False), start=1)
    )


def extract_inspection_assets(
    video: Path,
    shots: tuple[Shot, ...],
    output_dir: Path,
    *,
    runner: Runner = subprocess.run,
) -> tuple[Path, ...]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    for shot in shots:
        frame = output_dir / f"{shot.shot_id}.jpg"
        midpoint = (shot.start_ms + shot.end_ms) / 2_000
        _run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-ss",
                f"{midpoint:.3f}",
                "-i",
                str(video),
                "-frames:v",
                "1",
                str(frame),
            ],
            runner,
        )
        frames.append(frame)
    return tuple(frames)


def _anchor_timestamps(start_ms: int, end_ms: int) -> tuple[int, int, int]:
    duration_ms = end_ms - start_ms
    if duration_ms <= 160:
        return (
            start_ms + duration_ms // 4,
            start_ms + duration_ms // 2,
            start_ms + (duration_ms * 3) // 4,
        )
    return start_ms + 80, start_ms + duration_ms // 2, end_ms - 80


def extract_span_anchors(
    video: Path,
    document: NarrationSpanDocument,
    output_dir: Path,
    *,
    timeline: str,
    runner: Runner = subprocess.run,
) -> FrameAnchorDocument:
    if not video.is_file():
        raise MvpError(f"anchor video does not exist: {video}")
    if timeline != "SOURCE":
        raise MvpError("locked span ranges can only produce SOURCE anchors")
    output_dir.mkdir(parents=True, exist_ok=True)
    anchors: list[FrameAnchor] = []
    for span in document.spans:
        for source_range in span.source_ranges:
            for position, timestamp_ms in zip(
                ("START", "MIDDLE", "END"),
                _anchor_timestamps(
                    source_range.source_start_ms,
                    source_range.source_end_ms,
                ),
                strict=True,
            ):
                anchor_id = f"{span.span_id}-{source_range.range_id}-{position.lower()}"
                frame = output_dir / f"{anchor_id}.jpg"
                _run(
                    [
                        "ffmpeg",
                        "-y",
                        "-v",
                        "error",
                        "-ss",
                        f"{timestamp_ms / 1_000:.3f}",
                        "-i",
                        str(video),
                        "-frames:v",
                        "1",
                        str(frame),
                    ],
                    runner,
                )
                anchors.append(
                    FrameAnchor(
                        anchor_id,
                        span.span_id,
                        source_range.range_id,
                        timeline,
                        position,
                        timestamp_ms,
                        str(frame.resolve()),
                    )
                )
    result = FrameAnchorDocument(tuple(anchors))
    dump_json(output_dir / "anchors.json", result)
    return result


def extract_program_anchors(
    video: Path,
    edl: SpanEdlDocument,
    output_dir: Path,
    *,
    runner: Runner = subprocess.run,
) -> FrameAnchorDocument:
    if not video.is_file():
        raise MvpError(f"anchor video does not exist: {video}")
    output_dir.mkdir(parents=True, exist_ok=True)
    anchors: list[FrameAnchor] = []
    for segment in edl.segments:
        for position, timestamp_ms in zip(
            ("START", "MIDDLE", "END"),
            _anchor_timestamps(segment.program_start_ms, segment.program_end_ms),
            strict=True,
        ):
            anchor_id = f"{segment.span_id}-{segment.range_id}-program-{position.lower()}"
            frame = output_dir / f"{anchor_id}.jpg"
            _run(
                [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-ss",
                    f"{timestamp_ms / 1_000:.3f}",
                    "-i",
                    str(video),
                    "-frames:v",
                    "1",
                    "-strict",
                    "-2",
                    str(frame),
                ],
                runner,
            )
            anchors.append(
                FrameAnchor(
                    anchor_id,
                    segment.span_id,
                    segment.range_id,
                    "PROGRAM",
                    position,
                    timestamp_ms,
                    str(frame.resolve()),
                )
            )
    result = FrameAnchorDocument(tuple(anchors))
    dump_json(output_dir / "anchors.json", result)
    return result
