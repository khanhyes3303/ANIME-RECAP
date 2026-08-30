from __future__ import annotations

from dataclasses import dataclass

from .errors import MvpError
from .situation_validation import validate_keep_skip
from .situations import EditorialPolicy, NarrationPlan, SituationTtsManifest


@dataclass(frozen=True, slots=True)
class AdaptiveEdlSegment:
    segment_id: str
    unit_id: str
    situation_id: str
    range_id: str
    source_start_ms: int
    source_end_ms: int
    program_start_ms: int
    program_end_ms: int
    playback_rate: float
    shot_ids: tuple[str, ...]
    event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.segment_id.strip() or not self.unit_id.strip() or not self.range_id.strip():
            raise MvpError("adaptive EDL segment IDs must not be empty")
        if self.source_start_ms < 0 or self.source_end_ms <= self.source_start_ms:
            raise MvpError("adaptive EDL source interval is invalid")
        if self.program_start_ms < 0 or self.program_end_ms <= self.program_start_ms:
            raise MvpError("adaptive EDL program interval is invalid")
        if self.playback_rate <= 0:
            raise MvpError("adaptive EDL playback rate must be positive")


@dataclass(frozen=True, slots=True)
class AdaptiveEdlDocument:
    segments: tuple[AdaptiveEdlSegment, ...]
    total_duration_ms: int

    def __post_init__(self) -> None:
        if not self.segments:
            raise MvpError("adaptive EDL requires segments")
        if self.total_duration_ms <= 0:
            raise MvpError("adaptive EDL total duration must be positive")
        if self.segments[-1].program_end_ms != self.total_duration_ms:
            raise MvpError("adaptive EDL total duration does not match its segments")


def choose_playback_rate(
    footage_ms: int,
    voice_ms: int,
    policy: EditorialPolicy,
) -> float:
    if footage_ms <= 0 or voice_ms <= 0:
        raise MvpError("footage and voice durations must be positive")
    rate = footage_ms / voice_ms
    if not policy.minimum_playback_rate <= rate <= policy.maximum_playback_rate:
        raise MvpError(
            "rewrite narration or select evidence; required playback rate is outside policy"
        )
    return rate


def build_adaptive_edl(
    plan: NarrationPlan,
    tts: SituationTtsManifest,
    *,
    source_duration_ms: int,
    policy: EditorialPolicy,
) -> AdaptiveEdlDocument:
    if plan.policy_version != tts.policy_version:
        raise MvpError("narration and TTS policy versions must match")
    plan_ids = tuple(unit.unit_id for unit in plan.units)
    tts_ids = tuple(unit.unit_id for unit in tts.units)
    if plan_ids != tts_ids or len(set(tts_ids)) != len(tts_ids):
        raise MvpError("narration and TTS unit IDs must exactly match")
    validate_keep_skip(plan, source_duration_ms=source_duration_ms, policy=policy)

    tts_by_id = {item.unit_id: item for item in tts.units}
    program_cursor_ms = 0
    segments: list[AdaptiveEdlSegment] = []
    for unit in plan.units:
        if unit.status != "LOCKED":
            raise MvpError(f"adaptive EDL requires LOCKED unit: {unit.unit_id}")
        voice_ms = tts_by_id[unit.unit_id].duration_ms
        footage_ms = sum(
            item.source_end_ms - item.source_start_ms for item in unit.evidence_ranges
        )
        rate = choose_playback_rate(footage_ms, voice_ms, policy)
        unit_program_ms = 0
        for index, source_range in enumerate(unit.evidence_ranges, start=1):
            source_ms = source_range.source_end_ms - source_range.source_start_ms
            if index < len(unit.evidence_ranges):
                program_ms = round(source_ms / rate)
            else:
                program_ms = voice_ms - unit_program_ms
            if program_ms <= 0:
                raise MvpError("adaptive EDL rounding produced an empty segment")
            segments.append(
                AdaptiveEdlSegment(
                    segment_id=f"{unit.unit_id}-segment-{index:03d}",
                    unit_id=unit.unit_id,
                    situation_id=unit.situation_id,
                    range_id=source_range.range_id,
                    source_start_ms=source_range.source_start_ms,
                    source_end_ms=source_range.source_end_ms,
                    program_start_ms=program_cursor_ms,
                    program_end_ms=program_cursor_ms + program_ms,
                    playback_rate=rate,
                    shot_ids=source_range.shot_ids,
                    event_ids=source_range.event_ids,
                )
            )
            unit_program_ms += program_ms
            program_cursor_ms += program_ms
    if program_cursor_ms != tts.total_duration_ms:
        raise MvpError("adaptive EDL and narration durations do not match")
    return AdaptiveEdlDocument(tuple(segments), program_cursor_ms)
