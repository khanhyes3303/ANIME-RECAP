from __future__ import annotations

from dataclasses import dataclass

from .adaptive_edl import AdaptiveEdlDocument, AdaptiveEdlSegment
from .errors import MvpError
from .models import AuditFinding
from .situation_validation import validate_keep_skip
from .situations import CueTtsManifest, EditorialPolicy, NarrationPlan
from .tts import validate_cue_tts_ids


@dataclass(frozen=True, slots=True)
class CueTiming:
    cue_id: str
    spoken_start_ms: int
    spoken_end_ms: int
    visual_anchor_program_ms: int

    def __post_init__(self) -> None:
        if not self.cue_id.strip():
            raise MvpError("semantic cue ID must not be empty")
        if self.spoken_start_ms < 0 or self.spoken_end_ms <= self.spoken_start_ms:
            raise MvpError("semantic cue spoken interval is invalid")
        if self.visual_anchor_program_ms < 0:
            raise MvpError("semantic visual anchor is invalid")


@dataclass(frozen=True, slots=True)
class SemanticTimeline:
    cues: tuple[CueTiming, ...]
    total_duration_ms: int

    def __post_init__(self) -> None:
        if not self.cues or self.total_duration_ms <= 0:
            raise MvpError("semantic timeline must contain cues and duration")
        if any(cue.spoken_end_ms > self.total_duration_ms for cue in self.cues):
            raise MvpError("semantic cue exceeds timeline duration")


def map_source_timestamp(edl: AdaptiveEdlDocument, source_ms: int) -> int:
    for index, segment in enumerate(edl.segments):
        is_last = index == len(edl.segments) - 1
        if segment.source_start_ms <= source_ms < segment.source_end_ms or (
            is_last and source_ms == segment.source_end_ms
        ):
            offset = round((source_ms - segment.source_start_ms) / segment.playback_rate)
            return min(segment.program_start_ms + offset, segment.program_end_ms)
    raise MvpError(f"visual anchor is in omitted source footage: {source_ms}")


def _candidate_rates(policy: EditorialPolicy) -> tuple[float, ...]:
    minimum = round(policy.minimum_playback_rate * 1_000)
    maximum = round(policy.maximum_playback_rate * 1_000)
    rates = tuple(value / 1_000 for value in range(minimum, maximum + 1))
    return tuple(sorted(rates, key=lambda value: (abs(value - 1.0), value)))


def _unit_segments(
    plan: NarrationPlan,
    unit_index: int,
    rate: float,
    program_start_ms: int,
) -> tuple[AdaptiveEdlSegment, ...]:
    unit = plan.units[unit_index]
    cursor = program_start_ms
    result: list[AdaptiveEdlSegment] = []
    for index, source_range in enumerate(unit.evidence_ranges, start=1):
        duration = round(
            (source_range.source_end_ms - source_range.source_start_ms) / rate
        )
        if duration <= 0:
            raise MvpError("semantic EDL rounding produced an empty segment")
        result.append(
            AdaptiveEdlSegment(
                f"{unit.unit_id}-segment-{index:03d}",
                unit.unit_id,
                unit.situation_id,
                source_range.range_id,
                source_range.source_start_ms,
                source_range.source_end_ms,
                cursor,
                cursor + duration,
                rate,
                source_range.shot_ids,
                source_range.event_ids,
            )
        )
        cursor += duration
    return tuple(result)


def build_semantic_timeline(
    plan: NarrationPlan,
    tts: CueTtsManifest,
    source_duration_ms: int,
    policy: EditorialPolicy,
) -> tuple[AdaptiveEdlDocument, SemanticTimeline]:
    if plan.policy_version != "situation-v2" or tts.policy_version != "situation-v2":
        raise MvpError("semantic timeline requires situation-v2")
    validate_cue_tts_ids(plan, tts)
    validate_keep_skip(plan, source_duration_ms=source_duration_ms, policy=policy)
    tts_by_id = {cue.cue_id: cue for cue in tts.cues}
    segments: list[AdaptiveEdlSegment] = []
    timings: list[CueTiming] = []
    program_cursor = 0
    previous_spoken_end = -80

    for unit_index, unit in enumerate(plan.units):
        selected_segments: tuple[AdaptiveEdlSegment, ...] | None = None
        selected_timings: tuple[CueTiming, ...] | None = None
        for rate in _candidate_rates(policy):
            candidates = _unit_segments(plan, unit_index, rate, program_cursor)
            unit_end = candidates[-1].program_end_ms
            candidate_timings: list[CueTiming] = []
            cue_previous_end = previous_spoken_end
            valid = True
            for cue in unit.cues:
                try:
                    anchor = map_source_timestamp(
                        AdaptiveEdlDocument(candidates, unit_end),
                        cue.visual_anchor_source_ms,
                    )
                except MvpError:
                    valid = False
                    break
                spoken_start = max(
                    anchor + cue.visual_preroll_ms,
                    cue_previous_end + 80,
                )
                spoken_end = spoken_start + tts_by_id[cue.cue_id].duration_ms
                if spoken_end + cue.visual_postroll_ms > unit_end:
                    valid = False
                    break
                candidate_timings.append(
                    CueTiming(cue.cue_id, spoken_start, spoken_end, anchor)
                )
                cue_previous_end = spoken_end
            if valid:
                selected_segments = candidates
                selected_timings = tuple(candidate_timings)
                break
        if selected_segments is None or selected_timings is None:
            raise MvpError(
                "SEMANTIC_TIMELINE_DOES_NOT_FIT: rewrite narration or select more evidence"
            )
        segments.extend(selected_segments)
        timings.extend(selected_timings)
        program_cursor = selected_segments[-1].program_end_ms
        previous_spoken_end = selected_timings[-1].spoken_end_ms

    edl = AdaptiveEdlDocument(tuple(segments), program_cursor)
    return edl, SemanticTimeline(tuple(timings), program_cursor)


def semantic_timing_findings(
    cues: tuple[CueTiming, ...],
) -> tuple[AuditFinding, ...]:
    findings: list[AuditFinding] = []
    for cue in cues:
        if cue.spoken_start_ms + 100 < cue.visual_anchor_program_ms:
            lead = cue.visual_anchor_program_ms - cue.spoken_start_ms
            findings.append(
                AuditFinding(
                    "ERROR",
                    "VOICE_PRECEDES_VISUAL_ANCHOR",
                    cue.cue_id,
                    f"Voice starts at {cue.spoken_start_ms} ms, anchor is "
                    f"{cue.visual_anchor_program_ms} ms; lead is {lead} ms.",
                    (),
                )
            )
    return tuple(findings)
