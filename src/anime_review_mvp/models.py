from __future__ import annotations

from dataclasses import dataclass

from .errors import MvpError


def _non_empty(value: str, field: str) -> None:
    if not value.strip():
        raise MvpError(f"{field} must not be empty")


def _positive_interval(start_ms: int, end_ms: int, field: str) -> None:
    if start_ms < 0 or end_ms <= start_ms:
        raise MvpError(f"{field} interval is invalid")


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    start_ms: int
    end_ms: int
    characters: tuple[str, ...]
    description: str
    importance: str
    confidence: float

    def __post_init__(self) -> None:
        _non_empty(self.event_id, "event_id")
        _positive_interval(self.start_ms, self.end_ms, "event")
        _non_empty(self.description, "event description")
        _non_empty(self.importance, "event importance")
        if not 0 <= self.confidence <= 1:
            raise MvpError("event confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class SourceRegionAnnotation:
    region_id: str
    start_ms: int
    end_ms: int
    kind: str
    decision: str
    reason: str

    def __post_init__(self) -> None:
        _non_empty(self.region_id, "region_id")
        _positive_interval(self.start_ms, self.end_ms, "source region")
        if self.kind not in {"OPENING", "ENDING", "CREDITS", "NEXT_PREVIEW", "OTHER"}:
            raise MvpError("source region kind is invalid")
        if self.decision not in {"EXCLUDE", "KEEP_STORY"}:
            raise MvpError("source region decision is invalid")
        _non_empty(self.reason, "source region reason")


@dataclass(frozen=True, slots=True)
class TruthDocument:
    events: tuple[Event, ...]
    source_regions: tuple[SourceRegionAnnotation, ...]
    source_region_scan_complete: bool

    def __post_init__(self) -> None:
        if not self.events:
            raise MvpError("truth document requires events")
        if not self.source_region_scan_complete:
            raise MvpError("truth document requires a completed source-region scan")


@dataclass(frozen=True, slots=True)
class SourceRef:
    path: str
    sha256: str
    duration_ms: int
    width: int
    height: int
    time_base: str
    audio_stream_count: int


@dataclass(frozen=True, slots=True)
class TranscriptWord:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start_ms: int
    end_ms: int
    text: str
    words: tuple[TranscriptWord, ...]


@dataclass(frozen=True, slots=True)
class TranscriptDocument:
    language: str
    segments: tuple[TranscriptSegment, ...]


@dataclass(frozen=True, slots=True)
class Shot:
    shot_id: str
    start_ms: int
    end_ms: int

    def __post_init__(self) -> None:
        _non_empty(self.shot_id, "shot_id")
        _positive_interval(self.start_ms, self.end_ms, "shot")


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    kind: str
    text: str
    evidence_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _non_empty(self.claim_id, "claim_id")
        _non_empty(self.kind, "claim kind")
        _non_empty(self.text, "claim text")
        if not self.evidence_event_ids:
            raise MvpError("claim requires factual evidence")


@dataclass(frozen=True, slots=True)
class NarrationCue:
    cue_id: str
    text: str
    claim_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    directly_supported: bool

    def __post_init__(self) -> None:
        _non_empty(self.cue_id, "cue_id")
        _non_empty(self.text, "narration text")
        if not self.claim_ids or not self.event_ids:
            raise MvpError("narration cue requires claim and event bindings")


@dataclass(frozen=True, slots=True)
class ScriptDocument:
    cues: tuple[NarrationCue, ...]

    def __post_init__(self) -> None:
        if not self.cues:
            raise MvpError("script requires narration cues")


@dataclass(frozen=True, slots=True)
class TtsCue:
    cue_id: str
    mp3_path: str
    wav_path: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class TtsManifest:
    cues: tuple[TtsCue, ...]
    narration_wav_path: str
    provider: str
    voice_id: str


@dataclass(frozen=True, slots=True)
class EdlSegment:
    segment_id: str
    cue_id: str
    source_start_ms: int
    source_end_ms: int


@dataclass(frozen=True, slots=True)
class EdlDocument:
    segments: tuple[EdlSegment, ...]


@dataclass(frozen=True, slots=True)
class AuditFinding:
    severity: str
    code: str
    cue_id: str | None
    message: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AuditReport:
    passed: bool
    coverage_ratio: str
    findings: tuple[AuditFinding, ...]
