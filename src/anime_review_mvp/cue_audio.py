from __future__ import annotations

import subprocess
from collections.abc import Callable
from itertools import pairwise
from pathlib import Path
from typing import Any

from .errors import MvpError
from .semantic_timeline import SemanticTimeline
from .situations import CueTtsManifest

Runner = Callable[..., Any]


def _validate_alignment(tts: CueTtsManifest, timeline: SemanticTimeline) -> None:
    tts_ids = tuple(item.cue_id for item in tts.cues)
    timing_ids = tuple(item.cue_id for item in timeline.cues)
    if tts_ids != timing_ids:
        raise MvpError("cue audio IDs must exactly match semantic timeline")
    for current, following in pairwise(timeline.cues):
        if following.spoken_start_ms < current.spoken_end_ms:
            raise MvpError(
                f"cue audio timings overlap: {current.cue_id}, {following.cue_id}"
            )
    for audio, timing in zip(tts.cues, timeline.cues, strict=True):
        if timing.spoken_end_ms - timing.spoken_start_ms != audio.duration_ms:
            raise MvpError(f"cue audio duration does not match timeline: {audio.cue_id}")


def build_cue_audio_command(
    tts: CueTtsManifest,
    timeline: SemanticTimeline,
    output: Path,
) -> list[str]:
    _validate_alignment(tts, timeline)
    duration = timeline.total_duration_ms / 1_000
    command = [
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-t", f"{duration:.3f}",
        "-i", "anullsrc=r=44100:cl=mono",
    ]
    for cue in tts.cues:
        command.extend(("-i", cue.wav_path))
    filters: list[str] = []
    labels = ["[0:a]"]
    for index, timing in enumerate(timeline.cues, start=1):
        label = f"cue{index}"
        delay = timing.spoken_start_ms
        filters.append(f"[{index}:a]aresample=44100,adelay={delay}|{delay}[{label}]")
        labels.append(f"[{label}]")
    filters.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest,"
        f"atrim=duration={duration:.3f},asetpts=N/SR/TB[audio]"
    )
    command.extend(
        (
            "-filter_complex", ";".join(filters), "-map", "[audio]", "-c:a",
            "pcm_s16le", "-ar", "44100", "-ac", "1", str(output),
        )
    )
    return command


def render_cue_audio_timeline(
    tts: CueTtsManifest,
    timeline: SemanticTimeline,
    output: Path,
    *,
    runner: Runner = subprocess.run,
) -> Path:
    missing = [cue.wav_path for cue in tts.cues if not Path(cue.wav_path).is_file()]
    if missing:
        raise MvpError(f"cue WAV does not exist: {missing[0]}")
    output.parent.mkdir(parents=True, exist_ok=True)
    result = runner(
        build_cue_audio_command(tts, timeline, output),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MvpError(f"cue audio render failed: {(result.stderr or '').strip()}")
    if not output.is_file():
        raise MvpError("cue audio render did not create output")
    return output
