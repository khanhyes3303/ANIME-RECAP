from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation

from .errors import MvpError
from .models import (
    AuditReport,
    EdlDocument,
    ScriptDocument,
    TruthDocument,
    TtsManifest,
)

MINIMUM_COVERAGE = Decimal("0.80")
MAX_DURATION_DRIFT_MS = 40


def _duplicates(values: list[str]) -> bool:
    return len(values) != len(set(values))


def validate_truth(truth: TruthDocument, source_duration_ms: int) -> None:
    if source_duration_ms <= 0:
        raise MvpError("source duration must be positive")
    event_ids = [event.event_id for event in truth.events]
    region_ids = [region.region_id for region in truth.source_regions]
    if _duplicates(event_ids) or _duplicates(region_ids):
        raise MvpError("truth artifact contains duplicate IDs")
    for item in (*truth.events, *truth.source_regions):
        if item.end_ms > source_duration_ms:
            raise MvpError("truth timestamp exceeds source duration")
    ordered_regions = sorted(
        truth.source_regions, key=lambda region: (region.start_ms, region.end_ms)
    )
    for previous, current in zip(ordered_regions, ordered_regions[1:], strict=False):
        if current.start_ms < previous.end_ms:
            raise MvpError("source-region annotations overlap")


def validate_script(script: ScriptDocument, truth: TruthDocument) -> None:
    cue_ids = [cue.cue_id for cue in script.cues]
    if _duplicates(cue_ids):
        raise MvpError("script contains duplicate cue IDs")
    event_ids = {event.event_id for event in truth.events}
    for cue in script.cues:
        unknown = set(cue.event_ids) - event_ids
        if unknown:
            raise MvpError(f"cue references unknown event IDs: {sorted(unknown)}")


def coverage_ratio(script: ScriptDocument, tts: TtsManifest) -> Decimal:
    durations: dict[str, int] = {}
    for cue in tts.cues:
        if cue.cue_id in durations:
            raise MvpError("TTS manifest contains duplicate cue IDs")
        if cue.duration_ms <= 0:
            raise MvpError("TTS duration must be positive")
        durations[cue.cue_id] = cue.duration_ms
    script_ids = {cue.cue_id for cue in script.cues}
    if script_ids != set(durations):
        raise MvpError("script and TTS cue IDs must match exactly")
    total = sum(durations.values())
    if total <= 0:
        raise MvpError("TTS duration must be positive")
    supported = sum(
        durations[cue.cue_id] for cue in script.cues if cue.directly_supported
    )
    return Decimal(supported) / Decimal(total)


def validate_edl(
    edl: EdlDocument,
    source_duration_ms: int,
    tts: TtsManifest,
    truth: TruthDocument,
) -> None:
    if not edl.segments:
        raise MvpError("EDL requires segments")
    expected = {cue.cue_id: cue.duration_ms for cue in tts.cues}
    if _duplicates([segment.segment_id for segment in edl.segments]):
        raise MvpError("EDL contains duplicate segment IDs")
    grouped: dict[str, list[tuple[int, int]]] = defaultdict(list)
    excluded = [region for region in truth.source_regions if region.decision == "EXCLUDE"]
    for segment in edl.segments:
        if segment.cue_id not in expected:
            raise MvpError(f"EDL references unknown cue ID: {segment.cue_id}")
        if (
            segment.source_start_ms < 0
            or segment.source_end_ms <= segment.source_start_ms
            or segment.source_end_ms > source_duration_ms
        ):
            raise MvpError("EDL source interval is outside source bounds")
        for region in excluded:
            if max(segment.source_start_ms, region.start_ms) < min(
                segment.source_end_ms, region.end_ms
            ):
                raise MvpError("EDL intersects an excluded source region")
        grouped[segment.cue_id].append(
            (segment.source_start_ms, segment.source_end_ms)
        )

    if set(grouped) != set(expected):
        raise MvpError("EDL must provide footage for every TTS cue")
    for cue_id, intervals in grouped.items():
        for previous, current in zip(intervals, intervals[1:], strict=False):
            if current[0] < previous[1]:
                raise MvpError(f"EDL footage is not chronological for {cue_id}")
        footage_ms = sum(end - start for start, end in intervals)
        if abs(footage_ms - expected[cue_id]) > MAX_DURATION_DRIFT_MS:
            raise MvpError(
                f"footage duration for {cue_id} differs from TTS by more than "
                f"{MAX_DURATION_DRIFT_MS} ms"
            )


def validate_audit(audit: AuditReport, coverage: Decimal) -> None:
    errors = [finding for finding in audit.findings if finding.severity == "ERROR"]
    if errors:
        codes = ", ".join(finding.code for finding in errors)
        raise MvpError(f"audit has blocking errors: {codes}")
    if coverage < MINIMUM_COVERAGE:
        raise MvpError("direct evidence coverage must be at least 0.80")
    try:
        reported = Decimal(audit.coverage_ratio)
    except InvalidOperation as exc:
        raise MvpError("audit coverage_ratio is invalid") from exc
    if reported != coverage:
        raise MvpError("audit coverage_ratio does not match measured coverage")
    if not audit.passed:
        raise MvpError("audit did not pass")
