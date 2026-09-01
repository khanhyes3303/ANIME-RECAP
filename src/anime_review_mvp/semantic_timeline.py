from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from .adaptive_edl import AdaptiveEdlDocument, AdaptiveEdlSegment
from .errors import MvpError
from .models import AuditFinding, ShotDocument
from .situation_validation import validate_keep_skip
from .situations import CueTtsManifest, EditorialPolicy, NarrationPlan, cue_evidence_range
from .tts import validate_cue_tts_ids

MAX_NARRATION_GAP_MS = 600


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


@dataclass(frozen=True, slots=True)
class CueSourceWindow:
    source_start_ms: int
    source_end_ms: int
    playback_rate: float
    shot_ids: tuple[str, ...]


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


def _source_windows(
    evidence: object,
    cue: object,
    shots: ShotDocument | None,
) -> tuple[tuple[int, int, tuple[str, ...]], ...]:
    if shots is None:
        return (
            (
                evidence.source_start_ms,
                evidence.source_end_ms,
                evidence.shot_ids,
            ),
        )
    allowed = set(cue.shot_ids)
    ordered = tuple(
        shot
        for shot in shots.shots
        if shot.shot_id in allowed
        and shot.shot_id in evidence.shot_ids
        and shot.start_ms >= evidence.source_start_ms
        and shot.end_ms <= evidence.source_end_ms
    )
    windows: list[tuple[int, int, tuple[str, ...]]] = []
    for start_index in range(len(ordered)):
        selected: list[object] = []
        previous_end: int | None = None
        for shot in ordered[start_index:]:
            if previous_end is not None and shot.start_ms > previous_end + 1:
                break
            selected.append(shot)
            previous_end = shot.end_ms
            start_ms = selected[0].start_ms
            end_ms = shot.end_ms
            if start_ms <= cue.visual_anchor_source_ms < end_ms:
                windows.append(
                    (start_ms, end_ms, tuple(item.shot_id for item in selected))
                )
    return tuple(windows)


def select_cue_source_window(
    evidence: object,
    cue: object,
    shots: ShotDocument | None,
    *,
    voice_ms: int,
    policy: EditorialPolicy,
) -> CueSourceWindow:
    candidates: list[tuple[float, int, int, CueSourceWindow]] = []
    for source_start_ms, source_end_ms, shot_ids in _source_windows(evidence, cue, shots):
        source_ms = source_end_ms - source_start_ms
        anchor_offset_ms = cue.visual_anchor_source_ms - source_start_ms
        for rate in _candidate_rates(policy):
            program_ms = round(source_ms / rate)
            spoken_start_ms = round(anchor_offset_ms / rate) + cue.visual_preroll_ms
            spoken_end_ms = spoken_start_ms + voice_ms
            trailing_ms = program_ms - spoken_end_ms - cue.visual_postroll_ms
            if (
                spoken_start_ms > MAX_NARRATION_GAP_MS
                or trailing_ms < 0
                or trailing_ms + cue.visual_postroll_ms > MAX_NARRATION_GAP_MS
            ):
                continue
            candidates.append(
                (
                    abs(rate - 1.0),
                    trailing_ms,
                    program_ms,
                    CueSourceWindow(source_start_ms, source_end_ms, rate, shot_ids),
                )
            )
    if not candidates:
        evidence_ms = evidence.source_end_ms - evidence.source_start_ms
        raise MvpError(
            "SEMANTIC_TIMELINE_DOES_NOT_FIT: CUE_TIMELINE_DOES_NOT_FIT "
            f"cue_id={cue.cue_id} evidence_ms={evidence_ms} voice_ms={voice_ms} "
            f"rate={policy.minimum_playback_rate:.2f}-{policy.maximum_playback_rate:.2f}"
        )
    # When narration is shorter than accepted footage, prefer the shortest valid
    # visual window. This spends spare duration on playback speed instead of dead air.
    return min(candidates, key=lambda item: (item[2], item[0], item[1]))[3]


def build_semantic_timeline(
    plan: NarrationPlan,
    tts: CueTtsManifest,
    source_duration_ms: int,
    policy: EditorialPolicy,
    shots: ShotDocument | None = None,
    *,
    enforce_episode_duration: bool = True,
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

    segment_index = 0
    for unit in plan.units:
        for cue in unit.cues:
            evidence = cue_evidence_range(unit, cue)
            voice_ms = tts_by_id[cue.cue_id].duration_ms
            window = select_cue_source_window(
                evidence,
                cue,
                shots,
                voice_ms=voice_ms,
                policy=policy,
            )
            segment_index += 1
            program_ms = round(
                (window.source_end_ms - window.source_start_ms) / window.playback_rate
            )
            segment_end = program_cursor + program_ms
            anchor = program_cursor + round(
                (cue.visual_anchor_source_ms - window.source_start_ms) / window.playback_rate
            )
            spoken_start = max(anchor + cue.visual_preroll_ms, previous_spoken_end + 80)
            spoken_end = spoken_start + voice_ms
            gap_ms = (
                spoken_start - previous_spoken_end
                if previous_spoken_end >= 0
                else spoken_start
            )
            if (
                spoken_end + cue.visual_postroll_ms > segment_end
                or gap_ms > MAX_NARRATION_GAP_MS
            ):
                raise MvpError(
                    "SEMANTIC_TIMELINE_DOES_NOT_FIT: CUE_TIMELINE_DOES_NOT_FIT "
                    f"cue_id={cue.cue_id} gap_ms={gap_ms} voice_ms={voice_ms}"
                )
            segments.append(
                AdaptiveEdlSegment(
                    f"{unit.unit_id}-segment-{segment_index:03d}",
                    unit.unit_id,
                    unit.situation_id,
                    evidence.range_id,
                    window.source_start_ms,
                    window.source_end_ms,
                    program_cursor,
                    segment_end,
                    window.playback_rate,
                    window.shot_ids,
                    evidence.event_ids,
                )
            )
            timings.append(CueTiming(cue.cue_id, spoken_start, spoken_end, anchor))
            program_cursor = segment_end
            previous_spoken_end = spoken_end

    if enforce_episode_duration and not (
        policy.target_minimum_ms <= program_cursor <= policy.target_maximum_ms
    ):
        raise MvpError(
            "SEMANTIC_TIMELINE_DURATION_INVALID: Antigravity must revise accepted "
            "cue evidence to fit 7-12 minutes"
        )
    if timings and program_cursor - timings[-1].spoken_end_ms > MAX_NARRATION_GAP_MS:
        raise MvpError("SEMANTIC_TIMELINE_DOES_NOT_FIT: trailing footage lacks narration")
    edl = AdaptiveEdlDocument(tuple(segments), program_cursor)
    return edl, SemanticTimeline(tuple(timings), program_cursor)


def semantic_timing_findings(
    cues: tuple[CueTiming, ...],
    total_duration_ms: int | None = None,
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
    if (
        total_duration_ms is not None
        and cues
        and cues[0].spoken_start_ms > MAX_NARRATION_GAP_MS
    ):
        findings.append(
            AuditFinding(
                "ERROR",
                "LEADING_NARRATION_SILENCE",
                cues[0].cue_id,
                f"Narration starts after {cues[0].spoken_start_ms} ms of silence.",
                (),
            )
        )
    for current, following in pairwise(cues if total_duration_ms is not None else ()):
        gap_ms = following.spoken_start_ms - current.spoken_end_ms
        if gap_ms > MAX_NARRATION_GAP_MS:
            findings.append(
                AuditFinding(
                    "ERROR",
                    "NARRATION_GAP_TOO_LONG",
                    following.cue_id,
                    f"Narration gap is {gap_ms} ms; maximum is "
                    f"{MAX_NARRATION_GAP_MS} ms.",
                    (),
                )
            )
    if total_duration_ms is not None and cues:
        trailing_ms = total_duration_ms - cues[-1].spoken_end_ms
        if trailing_ms > MAX_NARRATION_GAP_MS:
            findings.append(
                AuditFinding(
                    "ERROR",
                    "TRAILING_NARRATION_SILENCE",
                    cues[-1].cue_id,
                    f"Video ends with {trailing_ms} ms of narration silence.",
                    (),
                )
            )
    return tuple(findings)
