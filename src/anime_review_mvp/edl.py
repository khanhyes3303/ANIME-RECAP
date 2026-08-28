from __future__ import annotations

from .errors import MvpError
from .models import (
    NarrationSpanDocument,
    SpanEdlDocument,
    SpanEdlSegment,
    SpanTtsManifest,
)


def _overlap(start_ms: int, end_ms: int, other_start_ms: int, other_end_ms: int) -> bool:
    return start_ms < other_end_ms and other_start_ms < end_ms


def build_edl_from_locked_spans(
    document: NarrationSpanDocument,
    tts: SpanTtsManifest,
    *,
    tolerance_ms: int = 80,
    minimum_segment_ms: int = 500,
) -> SpanEdlDocument:
    if tolerance_ms < 0 or minimum_segment_ms <= 0:
        raise MvpError("EDL timing limits must be positive")
    durations = {item.span_id: item.duration_ms for item in tts.spans}
    span_ids = [span.span_id for span in document.spans]
    if len(durations) != len(tts.spans) or set(durations) != set(span_ids):
        raise MvpError("locked spans and TTS span IDs must match")

    segments: list[SpanEdlSegment] = []
    used_ranges: list[tuple[int, int]] = []
    program_cursor_ms = 0
    for span in document.spans:
        footage_ms = sum(
            source_range.source_end_ms - source_range.source_start_ms
            for source_range in span.source_ranges
        )
        if abs(footage_ms - durations[span.span_id]) > tolerance_ms:
            raise MvpError(f"locked footage differs from TTS for {span.span_id}")
        for index, source_range in enumerate(span.source_ranges, start=1):
            duration_ms = source_range.source_end_ms - source_range.source_start_ms
            if duration_ms < minimum_segment_ms and not source_range.short_action_exception:
                raise MvpError(f"EDL segment must be at least {minimum_segment_ms} ms")
            if any(
                _overlap(
                    source_range.source_start_ms,
                    source_range.source_end_ms,
                    start_ms,
                    end_ms,
                )
                for start_ms, end_ms in used_ranges
            ):
                raise MvpError("locked EDL reuses overlapping source footage")
            used_ranges.append(
                (source_range.source_start_ms, source_range.source_end_ms)
            )
            segments.append(
                SpanEdlSegment(
                    segment_id=f"{span.span_id}-segment-{index:03d}",
                    span_id=span.span_id,
                    source_start_ms=source_range.source_start_ms,
                    source_end_ms=source_range.source_end_ms,
                    program_start_ms=program_cursor_ms,
                    program_end_ms=program_cursor_ms + duration_ms,
                    range_id=source_range.range_id,
                    scene_id=source_range.scene_id,
                    beat_id=source_range.beat_id,
                    shot_ids=source_range.shot_ids,
                    event_ids=source_range.event_ids,
                    short_action_exception=source_range.short_action_exception,
                )
            )
            program_cursor_ms += duration_ms
    return SpanEdlDocument(tuple(segments))
