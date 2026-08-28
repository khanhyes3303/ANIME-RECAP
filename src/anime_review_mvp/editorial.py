from __future__ import annotations

import re
from pathlib import Path

from .errors import MvpError
from .jsonio import load_json
from .models import NarrationSpanDocument, TruthDocument

_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")


def _duplicates(values: list[str]) -> bool:
    return len(values) != len(set(values))


def _overlap(start_ms: int, end_ms: int, other_start_ms: int, other_end_ms: int) -> bool:
    return start_ms < other_end_ms and other_start_ms < end_ms


def load_locked_spans(
    path: Path,
    truth: TruthDocument,
    source_duration_ms: int,
) -> NarrationSpanDocument:
    document = load_json(path, NarrationSpanDocument)
    if document.owner != "CODEX":
        raise MvpError("locked narration owner must be CODEX")
    if source_duration_ms <= 0:
        raise MvpError("source duration must be positive")

    span_ids = [span.span_id for span in document.spans]
    claim_ids = [claim.claim_id for claim in document.claims]
    if _duplicates(span_ids) or _duplicates(claim_ids):
        raise MvpError("locked narration IDs must be unique")

    known_events = {event.event_id for event in truth.events}
    known_claims = set(claim_ids)
    excluded = tuple(region for region in truth.source_regions if region.decision == "EXCLUDE")
    for claim in document.claims:
        if not set(claim.evidence_event_ids) <= known_events:
            raise MvpError("locked claim references an unknown event")
    for span in document.spans:
        if len(_SENTENCE_END.findall(span.text.strip())) != 1:
            raise MvpError(f"locked span {span.span_id} must contain one sentence")
        if not set(span.claim_ids) <= known_claims:
            raise MvpError("locked span references an unknown claim")
        if not set(span.event_ids) <= known_events:
            raise MvpError("locked span references an unknown event")
        for source_range in span.source_ranges:
            if source_range.source_end_ms > source_duration_ms:
                raise MvpError("locked source range exceeds source duration")
            if not set(source_range.event_ids) <= set(span.event_ids):
                raise MvpError("locked source range references an event outside its span")
            if any(
                _overlap(
                    source_range.source_start_ms,
                    source_range.source_end_ms,
                    region.start_ms,
                    region.end_ms,
                )
                for region in excluded
            ):
                raise MvpError("locked source range intersects an excluded source region")
    return document
