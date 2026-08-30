from __future__ import annotations

from itertools import pairwise

from .errors import MvpError
from .models import Shot, TruthDocument
from .situations import EditorialPolicy, NarrationPlan, SituationDocument


def _duplicates(values: list[str]) -> bool:
    return len(values) != len(set(values))


def _overlap(start_ms: int, end_ms: int, other_start_ms: int, other_end_ms: int) -> bool:
    return start_ms < other_end_ms and other_start_ms < end_ms


def validate_situations(
    document: SituationDocument,
    truth: TruthDocument,
    shots: tuple[Shot, ...],
    *,
    source_duration_ms: int,
) -> None:
    if source_duration_ms <= 0:
        raise MvpError("source duration must be positive")
    identifiers = [item.situation_id for item in document.situations]
    if _duplicates(identifiers):
        raise MvpError("situation IDs must be unique")
    known = set(identifiers)
    previous_end = -1
    for index, situation in enumerate(document.situations):
        if situation.source_end_ms > source_duration_ms:
            raise MvpError("situation exceeds source duration")
        if situation.source_start_ms < previous_end:
            raise MvpError("situations must follow source order without overlap")
        previous_end = situation.source_end_ms
        if situation.action_role == "DECORATIVE" and not (
            situation.new_information or situation.turning_points
        ):
            raise MvpError(f"situation {situation.situation_id} has no review value")
        if situation.story_role == "SUPPORTING_PLOT" and not situation.future_payoff.strip():
            raise MvpError("supporting plot requires a future payoff")
        expected_previous = document.situations[index - 1].situation_id if index else None
        expected_next = (
            document.situations[index + 1].situation_id
            if index + 1 < len(document.situations)
            else None
        )
        if situation.previous_situation_id not in {None, expected_previous}:
            raise MvpError("previous situation link is invalid")
        if situation.next_situation_id not in {None, expected_next}:
            raise MvpError("next situation link is invalid")
        if (
            situation.previous_situation_id is not None
            and situation.previous_situation_id not in known
        ):
            raise MvpError("previous situation link is unknown")
        if situation.next_situation_id is not None and situation.next_situation_id not in known:
            raise MvpError("next situation link is unknown")
        if not any(
            shot.start_ms < situation.source_end_ms and situation.source_start_ms < shot.end_ms
            for shot in shots
        ):
            raise MvpError("situation has no known source shot")
    if not truth.events:
        raise MvpError("situation validation requires source truth")


def validate_keep_skip(
    plan: NarrationPlan,
    *,
    source_duration_ms: int,
    policy: EditorialPolicy,
) -> None:
    ranges = [item for unit in plan.units for item in unit.evidence_ranges]
    if not ranges:
        raise MvpError("narration plan requires kept ranges")
    ordered = sorted(ranges, key=lambda item: (item.source_start_ms, item.source_end_ms))
    if ranges != ordered:
        raise MvpError("kept ranges must follow source order")
    if source_duration_ms <= 0 or ranges[-1].source_end_ms > source_duration_ms:
        raise MvpError("kept range exceeds source duration")
    for item in ranges:
        duration_ms = item.source_end_ms - item.source_start_ms
        if duration_ms < policy.minimum_clip_ms:
            raise MvpError(f"kept clip must be at least {policy.minimum_clip_ms} ms")
    for current, following in pairwise(ranges):
        gap_ms = following.source_start_ms - current.source_end_ms
        if gap_ms < policy.minimum_omitted_gap_ms:
            raise MvpError(
                f"omitted gap must be at least {policy.minimum_omitted_gap_ms} ms"
            )
    if source_duration_ms - ranges[-1].source_end_ms < policy.minimum_omitted_gap_ms:
        raise MvpError("final kept range requires an omitted source tail")


def _validate_shot_alignment(
    source_start_ms: int,
    source_end_ms: int,
    shot_ids: tuple[str, ...],
    shots: tuple[Shot, ...],
) -> None:
    selected = tuple(
        shot
        for shot in shots
        if shot.start_ms < source_end_ms and source_start_ms < shot.end_ms
    )
    if not selected:
        raise MvpError("kept range contains no source shot")
    if not (
        selected[0].start_ms <= source_start_ms < selected[0].end_ms
        and selected[-1].start_ms < source_end_ms <= selected[-1].end_ms
    ):
        raise MvpError("kept range is not covered by its source shots")
    if tuple(shot.shot_id for shot in selected) != shot_ids:
        raise MvpError("kept range shot IDs do not match its source interval")


def validate_narration_plan(
    plan: NarrationPlan,
    situations: SituationDocument,
    truth: TruthDocument,
    shots: tuple[Shot, ...],
    policy: EditorialPolicy,
    source_duration_ms: int,
) -> None:
    if plan.policy_version != situations.policy_version:
        raise MvpError("narration and situation policy versions must match")
    situation_by_id = {item.situation_id: item for item in situations.situations}
    known_events = {item.event_id for item in truth.events}
    excluded = tuple(item for item in truth.source_regions if item.decision == "EXCLUDE")
    unit_ids = [item.unit_id for item in plan.units]
    range_ids = [item.range_id for unit in plan.units for item in unit.evidence_ranges]
    if _duplicates(unit_ids) or _duplicates(range_ids):
        raise MvpError("narration unit and range IDs must be unique")
    for index, unit in enumerate(plan.units):
        try:
            situation = situation_by_id[unit.situation_id]
        except KeyError as exc:
            raise MvpError("narration unit references an unknown situation") from exc
        if index and not unit.bridge_from_previous.strip():
            raise MvpError("narration unit requires a bridge from the previous situation")
        if index + 1 < len(plan.units) and not unit.bridge_to_next.strip():
            raise MvpError("narration unit requires a bridge to the next situation")
        for source_range in unit.evidence_ranges:
            if source_range.situation_id != unit.situation_id:
                raise MvpError("evidence range belongs to another situation")
            if source_range.source_start_ms < policy.forbidden_before_ms:
                raise MvpError("kept range begins before the forbidden source timestamp")
            if not (
                situation.source_start_ms <= source_range.source_start_ms
                and source_range.source_end_ms <= situation.source_end_ms
            ):
                raise MvpError("kept range lies outside its situation")
            if not set(source_range.event_ids) <= known_events:
                raise MvpError("kept range references an unknown event")
            if any(
                _overlap(
                    source_range.source_start_ms,
                    source_range.source_end_ms,
                    region.start_ms,
                    region.end_ms,
                )
                for region in excluded
            ):
                raise MvpError("kept range intersects an excluded source region")
            _validate_shot_alignment(
                source_range.source_start_ms,
                source_range.source_end_ms,
                source_range.shot_ids,
                shots,
            )
    validate_keep_skip(plan, source_duration_ms=source_duration_ms, policy=policy)
