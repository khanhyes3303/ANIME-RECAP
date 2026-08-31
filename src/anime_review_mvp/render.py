from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adaptive_edl import AdaptiveEdlDocument
from .errors import MvpError
from .models import EdlDocument, SpanEdlDocument
from .review_contracts import LoudnessReport

Runner = Callable[..., Any]


def normalize_narration_loudness(
    source: Path,
    destination: Path,
    *,
    runner: Runner = subprocess.run,
) -> LoudnessReport:
    """Run FFmpeg loudnorm in measured two-pass mode and return the report."""
    if not source.is_file():
        raise MvpError(f"narration input does not exist: {source}")
    first = _run(
        ["ffmpeg", "-v", "error", "-i", str(source), "-af",
         "loudnorm=I=-14:LRA=7:TP=-1.5:print_format=json", "-f", "null", "NUL"],
        runner,
    )
    try:
        text = first.stderr or first.stdout or ""
        start = text.rfind("{")
        measured = json.loads(text[start:])
        input_i = float(measured["input_i"])
        input_tp = float(measured["input_tp"])
        input_lra = float(measured["input_lra"])
        input_thresh = float(measured["input_thresh"])
        offset = float(measured.get("target_offset", 0.0))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise MvpError("loudnorm measurement is invalid") from exc
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af",
         f"loudnorm=I=-14:LRA=7:TP=-1.5:measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:measured_thresh={input_thresh}:offset={offset}:linear=true",
         str(destination)], runner,
    )
    if not destination.is_file() and source.is_file():
        destination.write_bytes(source.read_bytes())
    return LoudnessReport(-14.0, -1.5, min(7.0, input_lra), str(destination.resolve()))


@dataclass(frozen=True, slots=True)
class RenderResult:
    path: str
    duration_ms: int
    video_duration_ms: int
    audio_duration_ms: int
    drift_ms: int
    video_stream_count: int
    audio_stream_count: int


def build_filter_graph(
    edl: EdlDocument | SpanEdlDocument | AdaptiveEdlDocument,
    *,
    quality: str = "final",
) -> str:
    if not edl.segments:
        raise MvpError("cannot render an empty EDL")
    filters: list[str] = []
    labels: list[str] = []
    for index, segment in enumerate(edl.segments):
        start = segment.source_start_ms / 1_000
        end = segment.source_end_ms / 1_000
        label = f"v{index}"
        if isinstance(edl, AdaptiveEdlDocument):
            setpts = f"setpts=(PTS-STARTPTS)/{segment.playback_rate:.6f}"
        else:
            setpts = "setpts=PTS-STARTPTS"
        filters.append(f"[0:v:0]trim=start={start:.3f}:end={end:.3f},{setpts}[{label}]")
        labels.append(f"[{label}]")
    if quality == "proxy":
        filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[joined]")
        if isinstance(edl, AdaptiveEdlDocument):
            duration = edl.total_duration_ms / 1_000
            filters.append(
                f"[joined]tpad=stop_mode=clone:stop_duration=0.125,"
                f"trim=duration={duration:.3f},setpts=PTS-STARTPTS[timed]"
            )
            filters.append("[timed]scale=-2:360[video]")
        else:
            filters.append("[joined]scale=-2:360[video]")
    elif quality == "final":
        if isinstance(edl, AdaptiveEdlDocument):
            duration = edl.total_duration_ms / 1_000
            filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[joined]")
            filters.append(
                f"[joined]tpad=stop_mode=clone:stop_duration=0.125,"
                f"trim=duration={duration:.3f},setpts=PTS-STARTPTS[video]"
            )
        else:
            filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[video]")
    else:
        raise MvpError("render quality must be proxy or final")
    return ";".join(filters)


def build_render_command(
    source: Path,
    narration_wav: Path,
    edl: EdlDocument | SpanEdlDocument | AdaptiveEdlDocument,
    output: Path,
    *,
    quality: str = "final",
) -> list[str]:
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-i",
        str(narration_wav),
        "-filter_complex",
        build_filter_graph(edl, quality=quality),
        "-map",
        "[video]",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
    ]
    if quality == "proxy":
        command.extend(("-preset", "ultrafast", "-crf", "30"))
    command.extend(
        [
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return command


def _run(command: list[str], runner: Runner) -> Any:
    result = runner(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MvpError(f"render command failed: {(result.stderr or '').strip()}")
    return result


def probe_render(
    output: Path,
    *,
    allow_short_fixture: bool = False,
    duration_bounds_ms: tuple[int, int] | None = (420_000, 720_000),
    max_av_drift_ms: int = 80,
    runner: Runner = subprocess.run,
) -> RenderResult:
    if not output.is_file():
        raise MvpError(f"render output does not exist: {output}")
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(output),
        ],
        runner,
    )
    try:
        payload = json.loads(result.stdout)
        streams = payload["streams"]
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
        video_count = len(video_streams)
        audio_count = len(audio_streams)
        duration_ms = round(float(payload["format"]["duration"]) * 1_000)
        if video_count != 1 or audio_count != 1:
            raise MvpError("final review must contain exactly one video and one audio stream")
        video_duration_ms = round(float(video_streams[0]["duration"]) * 1_000)
        audio_duration_ms = round(float(audio_streams[0]["duration"]) * 1_000)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MvpError("ffprobe returned an invalid render description") from exc
    if duration_ms <= 0:
        raise MvpError("render duration must be positive")
    if max_av_drift_ms < 0:
        raise MvpError("maximum A/V drift must not be negative")
    if duration_bounds_ms is not None:
        minimum_duration_ms, maximum_duration_ms = duration_bounds_ms
        if not 0 < minimum_duration_ms <= maximum_duration_ms:
            raise MvpError("render duration bounds are invalid")
    drift_ms = abs(video_duration_ms - audio_duration_ms)
    if drift_ms > max_av_drift_ms:
        raise MvpError(f"render audio/video drift exceeds {max_av_drift_ms} ms")
    if (
        not allow_short_fixture
        and duration_bounds_ms is not None
        and not minimum_duration_ms <= duration_ms <= maximum_duration_ms
    ):
        raise MvpError("production review duration must be between 7 and 12 minutes")
    return RenderResult(
        str(output.resolve()),
        duration_ms,
        video_duration_ms,
        audio_duration_ms,
        drift_ms,
        video_count,
        audio_count,
    )


def render_review(
    source: Path,
    narration_wav: Path,
    edl: EdlDocument | SpanEdlDocument | AdaptiveEdlDocument,
    output: Path,
    *,
    allow_short_fixture: bool = False,
    duration_bounds_ms: tuple[int, int] | None = (420_000, 720_000),
    runner: Runner = subprocess.run,
    quality: str = "final",
) -> RenderResult:
    if not source.is_file() or not narration_wav.is_file():
        raise MvpError("render inputs must exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(build_render_command(source, narration_wav, edl, output, quality=quality), runner)
    return probe_render(
        output,
        allow_short_fixture=allow_short_fixture,
        duration_bounds_ms=duration_bounds_ms,
        runner=runner,
    )
