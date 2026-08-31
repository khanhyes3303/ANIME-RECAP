from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .adaptive_edl import AdaptiveEdlDocument
from .errors import MvpError
from .jsonio import dump_json
from .media import capture_frame
from .models import TranscriptDocument
from .semantic_timeline import SemanticTimeline
from .situation_index import SituationIndexDocument
from .situation_validation import validate_edl_exclusions
from .situations import NarrationPlan, cue_evidence_range

Runner = Callable[..., object]
_FRAME_POSITIONS = ("START", "ANCHOR", "MIDDLE", "END")


@dataclass(frozen=True, slots=True)
class ProxyEvidenceFrame:
    position: str
    timestamp_ms: int
    path: str

    def __post_init__(self) -> None:
        if self.position not in {"START", "ANCHOR", "MIDDLE", "END"}:
            raise MvpError("proxy evidence frame position is invalid")
        if self.timestamp_ms < 0:
            raise MvpError("proxy evidence frame timestamp must not be negative")
        if not self.path.strip():
            raise MvpError("proxy evidence frame path must not be empty")


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

    def __post_init__(self) -> None:
        if not self.cue_id.strip() or not self.situation_id.strip():
            raise MvpError("proxy evidence cue metadata is invalid")
        if self.source_interval_ms[0] < 0 or (
            self.source_interval_ms[1] <= self.source_interval_ms[0]
        ):
            raise MvpError("proxy evidence source interval is invalid")
        if self.program_interval_ms[0] < 0 or (
            self.program_interval_ms[1] <= self.program_interval_ms[0]
        ):
            raise MvpError("proxy evidence program interval is invalid")
        if len(self.source_frames) != 4 or len(self.program_frames) != 4:
            raise MvpError("proxy evidence requires four source and program frames")
        if not self.transcript_text and not self.shot_ids:
            raise MvpError("proxy evidence requires transcript or shot evidence")


@dataclass(frozen=True, slots=True)
class BoundaryProxyEvidence:
    boundary: str
    program_frames: tuple[ProxyEvidenceFrame, ...]
    adjacent_excluded_source_intervals_ms: tuple[tuple[int, int], ...]
    transcript_segment_indexes: tuple[int, ...]

    def __post_init__(self) -> None:
        if self.boundary not in {"START", "END"}:
            raise MvpError("proxy evidence boundary is invalid")
        if not self.program_frames:
            raise MvpError("proxy boundary evidence requires frames")


@dataclass(frozen=True, slots=True)
class ProxyEvidenceManifest:
    cues: tuple[CueProxyEvidence, ...]
    boundaries: tuple[BoundaryProxyEvidence, ...]

    def __post_init__(self) -> None:
        if not self.cues:
            raise MvpError("proxy evidence manifest requires cues")
        if not self.boundaries:
            raise MvpError("proxy evidence manifest requires boundary evidence")


def _overlaps(start_ms: int, end_ms: int, other_start_ms: int, other_end_ms: int) -> bool:
    return max(start_ms, other_start_ms) < min(end_ms, other_end_ms)


def _frame_bundle(
    video: Path,
    start_ms: int,
    end_ms: int,
    anchor_ms: int,
    output_dir: Path,
    *,
    runner: Runner,
    strict_jpeg: bool,
) -> tuple[ProxyEvidenceFrame, ...]:
    if start_ms < 0 or end_ms <= start_ms:
        raise MvpError("proxy evidence interval is invalid")
    # A timing anchor can land exactly on a rounded EDL boundary. Clamp it to
    # the last real frame instead of asking the operator to repair harmless
    # one-millisecond rounding.
    anchor_ms = min(max(anchor_ms, start_ms), end_ms - 1)
    midpoint = (start_ms + end_ms) // 2
    timestamps = (
        ("START", start_ms),
        ("ANCHOR", anchor_ms),
        ("MIDDLE", midpoint),
        ("END", max(start_ms, end_ms - 1)),
    )
    frames: list[ProxyEvidenceFrame] = []
    for position, timestamp_ms in timestamps:
        frame = output_dir / f"{position.lower()}-{timestamp_ms:08d}.jpg"
        capture_frame(
            video,
            timestamp_ms,
            frame,
            runner=runner,
            strict_jpeg=strict_jpeg,
        )
        frames.append(ProxyEvidenceFrame(position, timestamp_ms, str(frame.resolve())))
    return tuple(frames)


def _cue_transcript_indexes(
    transcript: TranscriptDocument,
    start_ms: int,
    end_ms: int,
    transcript_refs: tuple[str, ...] = (),
) -> tuple[int, ...]:
    overlapping = tuple(
        index
        for index, segment in enumerate(transcript.segments)
        if _overlaps(start_ms, end_ms, segment.start_ms, segment.end_ms)
    )
    if not transcript_refs:
        return overlapping
    referenced = tuple(
        index for index in overlapping if transcript.segments[index].text in set(transcript_refs)
    )
    if len(referenced) != len(set(transcript_refs)):
        raise MvpError("proxy cue transcript references do not resolve exactly")
    return referenced


def extract_cue_proxy_evidence(
    source_video: Path,
    proxy_video: Path,
    plan: NarrationPlan,
    timeline: SemanticTimeline,
    edl: AdaptiveEdlDocument,
    index: SituationIndexDocument,
    transcript: TranscriptDocument,
    output_dir: Path,
    *,
    runner: Runner = subprocess.run,
) -> ProxyEvidenceManifest:
    validate_edl_exclusions(edl, index)
    if not source_video.is_file():
        raise MvpError(f"source video does not exist: {source_video}")
    if not proxy_video.is_file():
        raise MvpError(f"proxy video does not exist: {proxy_video}")
    if not plan.units:
        raise MvpError("proxy evidence requires narration units")
    if len(timeline.cues) != len({cue.cue_id for cue in timeline.cues}):
        raise MvpError("proxy evidence timeline cue IDs must be unique")

    cue_timings = {cue.cue_id: cue for cue in timeline.cues}
    units_by_situation = {unit.situation_id: unit for unit in plan.units}
    if len(units_by_situation) != len(plan.units):
        raise MvpError("proxy evidence unit situation IDs must be unique")
    excluded = tuple(item for item in index.situations if item.excluded)
    kept = tuple(item for item in index.situations if not item.excluded)
    if not kept:
        raise MvpError("proxy evidence requires at least one kept situation")

    output_dir.mkdir(parents=True, exist_ok=True)
    cues: list[CueProxyEvidence] = []
    for unit in plan.units:
        unit_segments = tuple(
            segment for segment in edl.segments if segment.unit_id == unit.unit_id
        )
        if not unit_segments:
            raise MvpError("proxy evidence is missing a unit EDL segment")
        for cue in unit.cues:
            timing = cue_timings.get(cue.cue_id)
            if timing is None:
                raise MvpError("proxy evidence timeline cue IDs do not match plan cues")
            evidence = cue_evidence_range(unit, cue)
            range_segments = tuple(
                segment for segment in unit_segments if segment.range_id == evidence.range_id
            )
            if len(range_segments) != 1:
                raise MvpError("proxy evidence cue range does not map exactly once")
            source_start_ms = evidence.source_start_ms
            source_end_ms = evidence.source_end_ms
            transcript_indexes = _cue_transcript_indexes(
                transcript,
                source_start_ms,
                source_end_ms,
                cue.transcript_refs,
            )
            transcript_text = tuple(transcript.segments[index].text for index in transcript_indexes)
            cue_output = output_dir / cue.cue_id
            cues.append(
                CueProxyEvidence(
                    cue.cue_id,
                    cue.situation_id,
                    (source_start_ms, source_end_ms),
                    (timing.spoken_start_ms, timing.spoken_end_ms),
                    _frame_bundle(
                        source_video,
                        source_start_ms,
                        source_end_ms,
                        cue.visual_anchor_source_ms,
                        cue_output / "source",
                        runner=runner,
                        strict_jpeg=False,
                    ),
                    _frame_bundle(
                        proxy_video,
                        timing.spoken_start_ms,
                        timing.spoken_end_ms,
                        timing.visual_anchor_program_ms,
                        cue_output / "program",
                        runner=runner,
                        strict_jpeg=True,
                    ),
                    transcript_indexes,
                    transcript_text,
                    evidence.shot_ids,
                )
            )

    start_kept = kept[0]
    end_kept = kept[-1]
    start_segments = tuple(
        segment for segment in edl.segments if segment.situation_id == start_kept.situation_id
    )
    end_segments = tuple(
        segment for segment in edl.segments if segment.situation_id == end_kept.situation_id
    )
    if not start_segments or not end_segments:
        raise MvpError("proxy evidence boundary segments are missing")
    start_program_start_ms = min(segment.program_start_ms for segment in start_segments)
    start_program_end_ms = max(segment.program_end_ms for segment in start_segments)
    end_program_start_ms = min(segment.program_start_ms for segment in end_segments)
    end_program_end_ms = max(segment.program_end_ms for segment in end_segments)
    start_excluded = tuple(
        (item.source_start_ms, item.source_end_ms)
        for item in excluded
        if item.source_end_ms <= start_kept.source_start_ms
    )
    end_excluded = tuple(
        (item.source_start_ms, item.source_end_ms)
        for item in excluded
        if item.source_start_ms >= end_kept.source_end_ms
    )
    boundary_output = output_dir / "boundaries"
    boundaries = (
        BoundaryProxyEvidence(
            "START",
            _frame_bundle(
                proxy_video,
                start_program_start_ms,
                start_program_end_ms,
                start_program_start_ms,
                boundary_output / "start",
                runner=runner,
                strict_jpeg=True,
            ),
            start_excluded,
            _cue_transcript_indexes(
                transcript,
                start_kept.source_start_ms,
                start_kept.source_end_ms,
            ),
        ),
        BoundaryProxyEvidence(
            "END",
            _frame_bundle(
                proxy_video,
                end_program_start_ms,
                max(end_program_start_ms, end_program_end_ms - 1),
                end_program_end_ms,
                boundary_output / "end",
                runner=runner,
                strict_jpeg=True,
            ),
            end_excluded,
            _cue_transcript_indexes(
                transcript,
                end_kept.source_start_ms,
                end_kept.source_end_ms,
            ),
        ),
    )
    manifest = ProxyEvidenceManifest(tuple(cues), boundaries)
    dump_json(output_dir / "proxy_evidence_manifest.json", manifest)
    return manifest
