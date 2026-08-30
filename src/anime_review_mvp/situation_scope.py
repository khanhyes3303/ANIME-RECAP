from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PurePath

from .errors import MvpError
from .jsonio import atomic_dump_json, load_json
from .models import Shot, ShotDocument, TranscriptDocument
from .situation_index import SituationIndexEntry
from .situations import NarrationPlan, SituationDocument


@dataclass(frozen=True, slots=True)
class ScopedFrameManifest:
    frames: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SituationScope:
    situation_id: str
    source_start_ms: int
    source_end_ms: int
    accepted_index_sha256: str
    transcript_path: str
    shots_path: str
    frames_path: str
    scope_path: str
    transcript_sha256: str
    shots_sha256: str
    frames_sha256: str

    @property
    def input_paths(self) -> tuple[str, ...]:
        return (self.transcript_path, self.shots_path, self.frames_path, self.scope_path)


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise MvpError(f"cannot hash situation scope file: {path}") from exc


def _intersects(start_ms: int, end_ms: int, item_start: int, item_end: int) -> bool:
    return item_end > start_ms and item_start < end_ms


def materialize_situation_scope(
    run_dir: Path,
    entry: SituationIndexEntry,
    transcript: TranscriptDocument,
    shots: ShotDocument,
    frame_refs: tuple[str, ...],
    *,
    accepted_index_sha256: str,
) -> SituationScope:
    if len(accepted_index_sha256) != 64:
        raise MvpError("accepted situation index hash is invalid")
    scoped_segments = tuple(
        segment
        for segment in transcript.segments
        if _intersects(
            entry.source_start_ms,
            entry.source_end_ms,
            segment.start_ms,
            segment.end_ms,
        )
    )
    scoped_shots = tuple(
        Shot(
            shot.shot_id,
            max(shot.start_ms, entry.source_start_ms),
            min(shot.end_ms, entry.source_end_ms),
        )
        for shot in shots.shots
        if shot.shot_id in entry.shot_ids
        and _intersects(
            entry.source_start_ms,
            entry.source_end_ms,
            shot.start_ms,
            shot.end_ms,
        )
    )
    scoped_shot_ids = {shot.shot_id for shot in scoped_shots}
    scoped_frames = tuple(
        frame
        for frame in frame_refs
        if frame in entry.frame_refs
        and PurePath(frame.replace("\\", "/")).stem in scoped_shot_ids
    )
    if not scoped_segments or not scoped_shots or not scoped_frames:
        raise MvpError("situation scope has no transcript, shot, or frame evidence")

    scope_dir = run_dir / "situation_inputs" / entry.situation_id
    transcript_path = scope_dir / "transcript.json"
    shots_path = scope_dir / "shots.json"
    frames_path = scope_dir / "frames.json"
    scope_path = scope_dir / "scope.json"
    atomic_dump_json(transcript_path, TranscriptDocument(transcript.language, scoped_segments))
    atomic_dump_json(shots_path, ShotDocument(scoped_shots))
    atomic_dump_json(frames_path, ScopedFrameManifest(scoped_frames))
    scope = SituationScope(
        entry.situation_id,
        entry.source_start_ms,
        entry.source_end_ms,
        accepted_index_sha256,
        str(transcript_path.resolve()),
        str(shots_path.resolve()),
        str(frames_path.resolve()),
        str(scope_path.resolve()),
        _sha256(transcript_path),
        _sha256(shots_path),
        _sha256(frames_path),
    )
    atomic_dump_json(scope_path, scope)
    return scope


def load_situation_scope(path: Path, *, verify_files: bool = False) -> SituationScope:
    scope = load_json(path, SituationScope)
    if verify_files:
        checks = (
            (Path(scope.transcript_path), scope.transcript_sha256),
            (Path(scope.shots_path), scope.shots_sha256),
            (Path(scope.frames_path), scope.frames_sha256),
        )
        if any(_sha256(file_path) != expected for file_path, expected in checks):
            raise MvpError("situation scope hash does not match its input files")
    return scope


def validate_submission_scope(
    entry: SituationIndexEntry,
    situations: SituationDocument,
    narration: NarrationPlan,
) -> None:
    if len(situations.situations) != 1:
        raise MvpError("submission must contain exactly one active situation")
    situation = situations.situations[0]
    if situation.situation_id != entry.situation_id or (
        situation.source_start_ms != entry.source_start_ms
        or situation.source_end_ms != entry.source_end_ms
    ):
        raise MvpError("submission situation is outside active situation boundary")
    allowed_shots = set(entry.shot_ids)
    allowed_frames = set(entry.frame_refs)
    for unit in narration.units:
        if unit.situation_id != entry.situation_id:
            raise MvpError("narration unit is outside active situation")
        for evidence in unit.evidence_ranges:
            if (
                evidence.situation_id != entry.situation_id
                or evidence.source_start_ms < entry.source_start_ms
                or evidence.source_end_ms > entry.source_end_ms
            ):
                raise MvpError("evidence range is outside active situation")
            if not set(evidence.shot_ids) <= allowed_shots or not set(
                evidence.frame_refs
            ) <= allowed_frames:
                raise MvpError("evidence reference is outside active situation")
        for cue in unit.cues:
            if not entry.source_start_ms <= cue.visual_anchor_source_ms < entry.source_end_ms:
                raise MvpError("visual anchor is outside active situation")
            if not set(cue.shot_ids) <= allowed_shots or not set(cue.frame_refs) <= allowed_frames:
                raise MvpError("cue evidence reference is outside active situation")
