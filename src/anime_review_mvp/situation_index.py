from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePath

from .errors import MvpError
from .jsonio import load_json
from .models import ShotDocument, SourceRef, TranscriptDocument


_SITUATION_ID = re.compile(r"situation-\d{3,}")


@dataclass(frozen=True, slots=True)
class SituationIndexEntry:
    situation_id: str
    source_start_ms: int
    source_end_ms: int
    summary: str
    story_purpose: str
    boundary_reason: str
    transcript_segment_indexes: tuple[int, ...]
    shot_ids: tuple[str, ...]
    frame_refs: tuple[str, ...]
    excluded: bool
    exclusion_reason: str

    def __post_init__(self) -> None:
        if not _SITUATION_ID.fullmatch(self.situation_id):
            raise MvpError("situation ID must use situation-NNN format")
        if self.source_start_ms < 0 or self.source_end_ms <= self.source_start_ms:
            raise MvpError("situation source range is invalid")
        if not all(
            value.strip()
            for value in (self.summary, self.story_purpose, self.boundary_reason)
        ):
            raise MvpError("situation summary, purpose, and boundary reason are required")
        if not self.transcript_segment_indexes and not self.shot_ids:
            raise MvpError("situation requires transcript or shot evidence")
        if len(set(self.transcript_segment_indexes)) != len(
            self.transcript_segment_indexes
        ) or len(set(self.shot_ids)) != len(self.shot_ids):
            raise MvpError("situation evidence references must be unique")
        if self.excluded and not self.exclusion_reason.strip():
            raise MvpError("excluded situation requires an exclusion reason")
        if not self.excluded and self.exclusion_reason.strip():
            raise MvpError("editable situation cannot have an exclusion reason")


@dataclass(frozen=True, slots=True)
class SituationIndexDocument:
    editor: str
    schema_version: str
    source_sha256: str
    situations: tuple[SituationIndexEntry, ...]

    def __post_init__(self) -> None:
        if self.editor != "ANTIGRAVITY":
            raise MvpError("situation index editor must be ANTIGRAVITY")
        if self.schema_version != "situation-index-v1":
            raise MvpError("situation index schema version is invalid")
        if len(self.source_sha256) != 64:
            raise MvpError("situation index source hash is invalid")
        if not self.situations:
            raise MvpError("situation index requires situations")


def _overlaps(start_ms: int, end_ms: int, item_start_ms: int, item_end_ms: int) -> bool:
    return item_end_ms > start_ms and item_start_ms < end_ms


def validate_situation_index(
    index: SituationIndexDocument,
    source: SourceRef,
    transcript: TranscriptDocument,
    shots: ShotDocument,
    frame_refs: tuple[str, ...],
) -> None:
    if index.source_sha256 != source.sha256:
        raise MvpError("situation index source hash does not match the episode")
    shot_by_id = {shot.shot_id: shot for shot in shots.shots}
    known_frames = set(frame_refs)
    seen_ids: set[str] = set()
    previous_end = -1
    editable = 0
    for entry in index.situations:
        if entry.situation_id in seen_ids:
            raise MvpError("situation IDs must be unique")
        seen_ids.add(entry.situation_id)
        if entry.source_end_ms > source.duration_ms:
            raise MvpError("situation range exceeds source duration")
        if entry.source_start_ms < previous_end:
            raise MvpError("situation ranges overlap or are not ordered")
        previous_end = entry.source_end_ms
        for segment_index in entry.transcript_segment_indexes:
            if segment_index < 0 or segment_index >= len(transcript.segments):
                raise MvpError("situation transcript reference does not exist")
            segment = transcript.segments[segment_index]
            if not _overlaps(
                entry.source_start_ms,
                entry.source_end_ms,
                segment.start_ms,
                segment.end_ms,
            ):
                raise MvpError("situation transcript reference is outside its range")
        for shot_id in entry.shot_ids:
            shot = shot_by_id.get(shot_id)
            if shot is None:
                raise MvpError("situation shot reference does not exist")
            if not _overlaps(
                entry.source_start_ms,
                entry.source_end_ms,
                shot.start_ms,
                shot.end_ms,
            ):
                raise MvpError("situation shot reference is outside its range")
        for frame_ref in entry.frame_refs:
            if frame_ref not in known_frames:
                raise MvpError("situation frame reference does not exist")
            frame_shot_id = PurePath(frame_ref.replace("\\", "/")).stem
            shot = shot_by_id.get(frame_shot_id)
            if shot is None or frame_shot_id not in entry.shot_ids or not _overlaps(
                entry.source_start_ms,
                entry.source_end_ms,
                shot.start_ms,
                shot.end_ms,
            ):
                raise MvpError("situation frame reference is outside its range")
        if not entry.excluded:
            editable += 1
    if editable == 0:
        raise MvpError("situation index requires at least one editable situation")


def load_situation_index(
    path: Path,
    source: SourceRef,
    transcript: TranscriptDocument,
    shots: ShotDocument,
    frame_refs: tuple[str, ...],
) -> SituationIndexDocument:
    index = load_json(path, SituationIndexDocument)
    validate_situation_index(index, source, transcript, shots, frame_refs)
    return index


def next_editable_situation(
    index: SituationIndexDocument, locked_ids: tuple[str, ...]
) -> SituationIndexEntry | None:
    locked = set(locked_ids)
    return next(
        (
            entry
            for entry in index.situations
            if not entry.excluded and entry.situation_id not in locked
        ),
        None,
    )
