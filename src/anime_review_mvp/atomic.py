from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .errors import MvpError
from .jsonio import load_json
from .models import (
    AtomicBeat,
    AtomicStoryboard,
    CriticReviewDocument,
    Shot,
    TruthDocument,
)


def _overlap(first_start: int, first_end: int, second_start: int, second_end: int) -> bool:
    return first_start < second_end and second_start < first_end


def _unique(values: list[str], label: str) -> None:
    if len(values) != len(set(values)):
        raise MvpError(f"duplicate {label} values are forbidden")


def _window_inside_footage(beat: AtomicBeat) -> bool:
    if beat.action_window_start_ms is None or beat.action_window_end_ms is None:
        return False
    if beat.action_window_end_ms <= beat.action_window_start_ms:
        return False
    return any(
        source_range.source_start_ms <= beat.action_window_start_ms
        and beat.action_window_end_ms <= source_range.source_end_ms
        for source_range in beat.source_ranges
    )


def load_atomic_storyboard(
    path: Path,
    truth: TruthDocument,
    shots: tuple[Shot, ...],
    source_duration_ms: int,
) -> AtomicStoryboard:
    document = load_json(path, AtomicStoryboard)
    if document.owner != "ANTIGRAVITY":
        raise MvpError("atomic storyboard owner must be ANTIGRAVITY")
    if source_duration_ms <= 0:
        raise MvpError("source duration must be positive")
    _unique([claim.claim_id for claim in document.claims], "claim_id")
    _unique([beat.beat_id for beat in document.beats], "beat_id")
    known_claims = {claim.claim_id for claim in document.claims}
    known_events = {event.event_id for event in truth.events}
    known_shots = {shot.shot_id for shot in shots}
    excluded = tuple(region for region in truth.source_regions if region.decision == "EXCLUDE")

    for claim in document.claims:
        if not set(claim.evidence_event_ids) <= known_events:
            raise MvpError("atomic claim references an unknown event")
    for beat in document.beats:
        if not set(beat.claim_ids) <= known_claims or not set(beat.event_ids) <= known_events:
            raise MvpError("atomic beat references unknown claim or event")
        for source_range in beat.source_ranges:
            if source_range.beat_id != beat.beat_id or source_range.scene_id != beat.scene_id:
                raise MvpError("atomic source range belongs to another beat or scene")
            if source_range.source_end_ms > source_duration_ms:
                raise MvpError("atomic source range exceeds source duration")
            if not set(source_range.shot_ids) <= known_shots:
                raise MvpError("atomic source range references an unknown shot")
            if not set(source_range.event_ids) <= set(beat.event_ids):
                raise MvpError("atomic source range event is outside its beat")
            if any(
                _overlap(
                    source_range.source_start_ms,
                    source_range.source_end_ms,
                    region.start_ms,
                    region.end_ms,
                )
                for region in excluded
            ):
                raise MvpError("atomic source range intersects excluded footage")
        if beat.sync_mode == "CONTEXT":
            if beat.action_window_start_ms is not None or beat.action_window_end_ms is not None:
                raise MvpError("CONTEXT beat must not declare an action window")
        elif not _window_inside_footage(beat):
            raise MvpError("atomic action window must be inside selected footage")
    return document


def load_critic_review(
    path: Path,
    storyboard: AtomicStoryboard,
    phase: str,
) -> CriticReviewDocument:
    review = load_json(path, CriticReviewDocument)
    if review.phase != phase:
        raise MvpError("critic review phase does not match")
    if review.producer_context_id != storyboard.producer_context_id:
        raise MvpError("critic review producer context does not match storyboard")
    if review.critic_context_id == review.producer_context_id:
        raise MvpError("producer and critic require separate contexts")
    review_ids = [item.beat_id for item in review.beat_reviews]
    _unique(review_ids, "critic beat_id")
    if set(review_ids) != {beat.beat_id for beat in storyboard.beats}:
        raise MvpError("critic review must cover every atomic beat")
    return review


def beat_cache_key(beat: AtomicBeat, voice_id: str, policy_version: str) -> str:
    payload = {
        "beat": asdict(beat),
        "voice_id": voice_id,
        "policy_version": policy_version,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
