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
            raise MvpError(f"cue audio timings overlap: {current.cue_id}, {following.cue_id}")
    for audio, timing in zip(tts.cues, timeline.cues, strict=True):
        if timing.spoken_end_ms - timing.spoken_start_ms != audio.duration_ms:
            raise MvpError(f"cue audio duration does not match timeline: {audio.cue_id}")


def build_cue_audio_command(
    tts: CueTtsManifest,
    timeline: SemanticTimeline,
    output: Path,
    *,
    cue_gains_db: tuple[float, ...] | None = None,
) -> list[str]:
    _validate_alignment(tts, timeline)
    gains = cue_gains_db or tuple(0.0 for _ in tts.cues)
    if len(gains) != len(tts.cues):
        raise MvpError("cue gain count must exactly match cue audio")
    duration = timeline.total_duration_ms / 1_000
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-t",
        f"{duration:.3f}",
        "-i",
        "anullsrc=r=48000:cl=mono",
    ]
    for cue in tts.cues:
        command.extend(("-i", cue.wav_path))
    filters: list[str] = []
    labels = ["[0:a]"]
    for index, (timing, gain_db) in enumerate(zip(timeline.cues, gains, strict=True), start=1):
        label = f"cue{index}"
        delay = timing.spoken_start_ms
        filters.append(
            f"[{index}:a]volume={gain_db:.3f}dB,alimiter=limit=0.794,"
            f"aresample=48000,adelay={delay}|{delay}[{label}]"
        )
        labels.append(f"[{label}]")
    filters.append(
        f"{''.join(labels)}amix=inputs={len(labels)}:duration=longest:normalize=0,"
        f"atrim=duration={duration:.3f},asetpts=N/SR/TB[audio]"
    )
    command.extend(
        (
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[audio]",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "1",
            str(output),
        )
    )
    return command


def _cue_gain_db(path: str, runner: Runner) -> float:
    result = runner(
        [
            "ffmpeg",
            "-v",
            "info",
            "-i",
            path,
            "-af",
            "volumedetect",
            "-f",
            "null",
            "NUL",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MvpError(f"cue loudness measurement failed: {(result.stderr or '').strip()}")
    try:
        line = next(
            item
            for item in (result.stderr or result.stdout or "").splitlines()
            if "mean_volume:" in item
        )
        mean_db = float(line.split("mean_volume:", 1)[1].split("dB", 1)[0])
    except (StopIteration, ValueError, IndexError) as exc:
        raise MvpError("cue loudness measurement is invalid") from exc
    return max(-12.0, min(12.0, -18.0 - mean_db))


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
    gains = tuple(_cue_gain_db(cue.wav_path, runner) for cue in tts.cues)
    result = runner(
        build_cue_audio_command(tts, timeline, output, cue_gains_db=gains),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MvpError(f"cue audio render failed: {(result.stderr or '').strip()}")
    if not output.is_file():
        raise MvpError("cue audio render did not create output")
    return output
