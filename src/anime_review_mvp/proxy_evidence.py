from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .adaptive_edl import AdaptiveEdlDocument
from .errors import MvpError
from .models import ShotDocument, TranscriptDocument
from .semantic_timeline import SemanticTimeline, map_source_timestamp
from .situation_index import SituationIndexDocument
from .situations import NarrationPlan


@dataclass(frozen=True, slots=True)
class ProxyEvidenceFrame:
    position: str
    timestamp_ms: int
    path: str


@dataclass(frozen=True, slots=True)
class CueProxyEvidence:
    cue_id: str
    situation_id: str
    source_interval_ms: tuple[int, int]
    program_interval_ms: tuple[int, int]
    source_frames: tuple[ProxyEvidenceFrame, ...]
    program_frames: tuple[ProxyEvidenceFrame, ...]
    transcript_segment_indexes: tuple[int, ...]
    transcript_text: tuple[str, ...]
    shot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BoundaryProxyEvidence:
    boundary: str
    program_frames: tuple[ProxyEvidenceFrame, ...]
    adjacent_excluded_source_intervals_ms: tuple[tuple[int, int], ...]
    transcript_segment_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ProxyEvidenceManifest:
    cues: tuple[CueProxyEvidence, ...]
    boundaries: tuple[BoundaryProxyEvidence, ...]


def _capture(runner: Callable[..., object], video: Path, timestamp: int, position: str, output: Path) -> ProxyEvidenceFrame:
    result = runner(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{timestamp / 1000:.3f}",
         "-i", str(video), "-frames:v", "1", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    if getattr(result, "returncode", 0) != 0:
        raise MvpError("PROXY_EVIDENCE_FRAME_EXTRACTION_FAILED")
    path = str(output)
    return ProxyEvidenceFrame(position, timestamp, path)


def extract_cue_proxy_evidence(
    source: Path,
    proxy: Path,
    plan: NarrationPlan,
    timeline: SemanticTimeline,
    edl: AdaptiveEdlDocument,
    index: object,
    transcript: TranscriptDocument,
    output_dir: Path,
    *,
    runner: Callable[..., object],
) -> ProxyEvidenceManifest:
    del source
    output_dir.mkdir(parents=True, exist_ok=True)
    cues: list[CueProxyEvidence] = []
    for cue_timing, unit in zip(timeline.cues, plan.units, strict=False):
        cue = next((item for item in unit.cues if item.cue_id == cue_timing.cue_id), None)
        if cue is None:
            continue
        ranges = unit.evidence_ranges
        source_start = min(item.source_start_ms for item in ranges)
        source_end = max(item.source_end_ms for item in ranges)
        program_start = min(item.program_start_ms for item in edl.segments if item.unit_id == unit.unit_id)
        program_end = max(item.program_end_ms for item in edl.segments if item.unit_id == unit.unit_id)
        source_points = (source_start, cue.visual_anchor_source_ms, (source_start + source_end) // 2, source_end - 1)
        program_anchor = map_source_timestamp(edl, cue.visual_anchor_source_ms)
        program_points = (program_start, program_anchor, (program_start + program_end) // 2, max(program_start, program_end - 1))
        positions = ("START", "ANCHOR", "MIDDLE", "END")
        source_frames = tuple(_capture(runner, proxy, ts, pos, output_dir / f"{cue.cue_id}-source-{pos.lower()}.jpg") for ts, pos in zip(source_points, positions, strict=True))
        program_frames = tuple(_capture(runner, proxy, ts, pos, output_dir / f"{cue.cue_id}-program-{pos.lower()}.jpg") for ts, pos in zip(program_points, positions, strict=True))
        indexes = tuple(i for i, segment in enumerate(transcript.segments) if segment.end_ms > source_start and segment.start_ms < source_end)
        texts = tuple(transcript.segments[i].text for i in indexes)
        cues.append(CueProxyEvidence(cue.cue_id, cue.situation_id, (source_start, source_end), (program_start, program_end), source_frames, program_frames, indexes, texts, cue.shot_ids))
    if not cues:
        raise MvpError("PROXY_EVIDENCE_CUE_COVERAGE_INVALID")
    first = min(segment.program_start_ms for segment in edl.segments)
    last = max(segment.program_end_ms for segment in edl.segments)
    boundaries = (
        BoundaryProxyEvidence(
            "START",
            (_capture(runner, proxy, first, "START", output_dir / "boundary-start.jpg"),),
            tuple((item.source_start_ms, item.source_end_ms) for item in getattr(index, "situations", ()) if getattr(item, "excluded", False)),
            (),
        ),
        BoundaryProxyEvidence(
            "END",
            (_capture(runner, proxy, max(first, last - 1), "END", output_dir / "boundary-end.jpg"),),
            tuple((item.source_start_ms, item.source_end_ms) for item in getattr(index, "situations", ()) if getattr(item, "excluded", False)),
            (),
        ),
    )
    return ProxyEvidenceManifest(tuple(cues), boundaries)


def validate_edl_exclusions(edl: AdaptiveEdlDocument, index: SituationIndexDocument) -> None:
    for segment in edl.segments:
        for item in index.situations:
            if item.excluded and max(segment.source_start_ms, item.source_start_ms) < min(segment.source_end_ms, item.source_end_ms):
                raise MvpError("EDL_EXCLUDED_SOURCE_OVERLAP")
