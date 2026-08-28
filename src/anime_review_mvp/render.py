from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import MvpError
from .models import EdlDocument

Runner = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class RenderResult:
    path: str
    duration_ms: int
    video_stream_count: int
    audio_stream_count: int


def build_filter_graph(edl: EdlDocument) -> str:
    if not edl.segments:
        raise MvpError("cannot render an empty EDL")
    filters: list[str] = []
    labels: list[str] = []
    for index, segment in enumerate(edl.segments):
        start = segment.source_start_ms / 1_000
        end = segment.source_end_ms / 1_000
        label = f"v{index}"
        filters.append(
            f"[0:v:0]trim=start={start:.3f}:end={end:.3f},"
            f"setpts=PTS-STARTPTS[{label}]"
        )
        labels.append(f"[{label}]")
    filters.append(
        f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[video]"
    )
    return ";".join(filters)


def build_render_command(
    source: Path,
    narration_wav: Path,
    edl: EdlDocument,
    output: Path,
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-i",
        str(narration_wav),
        "-filter_complex",
        build_filter_graph(edl),
        "-map",
        "[video]",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        "-shortest",
        str(output),
    ]


def _run(command: list[str], runner: Runner) -> Any:
    result = runner(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise MvpError(f"render command failed: {(result.stderr or '').strip()}")
    return result


def probe_render(
    output: Path,
    *,
    allow_short_fixture: bool = False,
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
        video_count = sum(stream.get("codec_type") == "video" for stream in streams)
        audio_count = sum(stream.get("codec_type") == "audio" for stream in streams)
        duration_ms = round(float(payload["format"]["duration"]) * 1_000)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MvpError("ffprobe returned an invalid render description") from exc
    if video_count != 1 or audio_count != 1:
        raise MvpError("final review must contain exactly one video and one audio stream")
    if duration_ms <= 0:
        raise MvpError("render duration must be positive")
    if not allow_short_fixture and not 420_000 <= duration_ms <= 720_000:
        raise MvpError("production review duration must be between 7 and 12 minutes")
    return RenderResult(str(output.resolve()), duration_ms, video_count, audio_count)


def render_review(
    source: Path,
    narration_wav: Path,
    edl: EdlDocument,
    output: Path,
    *,
    allow_short_fixture: bool = False,
    runner: Runner = subprocess.run,
) -> RenderResult:
    if not source.is_file() or not narration_wav.is_file():
        raise MvpError("render inputs must exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(build_render_command(source, narration_wav, edl, output), runner)
    return probe_render(
        output, allow_short_fixture=allow_short_fixture, runner=runner
    )
