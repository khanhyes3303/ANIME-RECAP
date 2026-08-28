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
class ShotDocument:
    shots: tuple[Shot, ...]

    def __post_init__(self) -> None:
        if not self.shots:
            raise MvpError("shot document requires shots")


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
class SpanSourceRange:
    range_id: str
    source_start_ms: int
    source_end_ms: int
    scene_id: str
    beat_id: str
    shot_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    short_action_exception: bool = False

    def __post_init__(self) -> None:
        _non_empty(self.range_id, "range_id")
        _positive_interval(self.source_start_ms, self.source_end_ms, "span source range")
        _non_empty(self.scene_id, "scene_id")
        _non_empty(self.beat_id, "beat_id")
        if not self.shot_ids:
            raise MvpError("span source range requires shot IDs")
        if not self.event_ids:
            raise MvpError("span source range requires event IDs")


@dataclass(frozen=True, slots=True)
class NarrationSpan:
    span_id: str
    text: str
    claim_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    characters: tuple[str, ...]
    visible_action: str
    source_ranges: tuple[SpanSourceRange, ...]

    def __post_init__(self) -> None:
        _non_empty(self.span_id, "span_id")
        _non_empty(self.text, "narration span text")
        _non_empty(self.visible_action, "visible_action")
        if not self.claim_ids or not self.event_ids:
            raise MvpError("narration span requires claim and event bindings")
        if not self.characters:
            raise MvpError("narration span requires visible characters")
        if not self.source_ranges:
            raise MvpError("narration span requires source ranges")


@dataclass(frozen=True, slots=True)
class NarrationSpanDocument:
    spans: tuple[NarrationSpan, ...]
    claims: tuple[Claim, ...]
    owner: str

    def __post_init__(self) -> None:
        if not self.spans:
            raise MvpError("locked narration requires spans")
        if not self.claims:
            raise MvpError("locked narration requires claims")
        _non_empty(self.owner, "locked narration owner")


@dataclass(frozen=True, slots=True)
class FrameAnchor:
    anchor_id: str
    span_id: str
    range_id: str
    timeline: str
    position: str
    timestamp_ms: int
    path: str

    def __post_init__(self) -> None:
        _non_empty(self.anchor_id, "anchor_id")
        _non_empty(self.span_id, "anchor span_id")
        _non_empty(self.range_id, "anchor range_id")
        if self.timeline not in {"SOURCE", "PROGRAM"}:
            raise MvpError("anchor timeline is invalid")
        if self.position not in {"START", "MIDDLE", "END"}:
            raise MvpError("anchor position is invalid")
        if self.timestamp_ms < 0:
            raise MvpError("anchor timestamp must not be negative")
        _non_empty(self.path, "anchor path")


@dataclass(frozen=True, slots=True)
class FrameAnchorDocument:
    anchors: tuple[FrameAnchor, ...]

    def __post_init__(self) -> None:
        if not self.anchors:
            raise MvpError("anchor document requires frames")


@dataclass(frozen=True, slots=True)
class NarrationCue:
    cue_id: str
    text: str
    claim_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    directly_supported: bool
    scene_id: str = ""
    beat_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _non_empty(self.cue_id, "cue_id")
        _non_empty(self.text, "narration text")
        if not self.claim_ids or not self.event_ids:
            raise MvpError("narration cue requires claim and event bindings")


@dataclass(frozen=True, slots=True)
class ScriptDocument:
    cues: tuple[NarrationCue, ...]
    claims: tuple[Claim, ...] = ()

    def __post_init__(self) -> None:
        if not self.cues:
            raise MvpError("script requires narration cues")


@dataclass(frozen=True, slots=True)
class SceneShot:
    shot_id: str
    start_ms: int
    end_ms: int
    role: str
    event_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        _non_empty(self.shot_id, "scene shot_id")
        _positive_interval(self.start_ms, self.end_ms, "scene shot")
        if self.role not in {"MUST_KEEP", "OPTIONAL", "TRANSITION"}:
            raise MvpError("scene shot role is invalid")
        _non_empty(self.reason, "scene shot reason")


@dataclass(frozen=True, slots=True)
class SceneBeat:
    beat_id: str
    start_ms: int
    end_ms: int
    event_ids: tuple[str, ...]
    shot_ids: tuple[str, ...]
    cue_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _non_empty(self.beat_id, "beat_id")
        _positive_interval(self.start_ms, self.end_ms, "beat")
        if not self.shot_ids:
            raise MvpError("beat requires shot IDs")
        if not self.cue_ids:
            raise MvpError("beat requires cue IDs")


@dataclass(frozen=True, slots=True)
class ScenePacket:
    scene_id: str
    start_ms: int
    end_ms: int
    story_purpose: str
    event_ids: tuple[str, ...]
    shots: tuple[SceneShot, ...]
    beats: tuple[SceneBeat, ...]
    cue_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _non_empty(self.scene_id, "scene_id")
        _positive_interval(self.start_ms, self.end_ms, "scene")
        _non_empty(self.story_purpose, "scene story purpose")
        if not self.event_ids:
            raise MvpError("scene requires event IDs")
        if not self.shots:
            raise MvpError("scene requires shots")
        if not self.beats:
            raise MvpError("scene requires beats")
        if not self.cue_ids:
            raise MvpError("scene requires cue IDs")


@dataclass(frozen=True, slots=True)
class ScenePacketDocument:
    packets: tuple[ScenePacket, ...]

    def __post_init__(self) -> None:
        if not self.packets:
            raise MvpError("scene packet document requires packets")


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
class SpanTts:
    span_id: str
    mp3_path: str
    wav_path: str
    duration_ms: int

    def __post_init__(self) -> None:
        _non_empty(self.span_id, "TTS span_id")
        _non_empty(self.mp3_path, "TTS span MP3 path")
        _non_empty(self.wav_path, "TTS span WAV path")
        if self.duration_ms <= 0:
            raise MvpError("TTS span duration must be positive")


@dataclass(frozen=True, slots=True)
class SpanTtsManifest:
    spans: tuple[SpanTts, ...]
    narration_wav_path: str
    provider: str
    voice_id: str

    def __post_init__(self) -> None:
        if not self.spans:
            raise MvpError("span TTS manifest requires audio")
        _non_empty(self.narration_wav_path, "narration WAV path")
        _non_empty(self.provider, "TTS provider")
        _non_empty(self.voice_id, "TTS voice_id")


@dataclass(frozen=True, slots=True)
class EdlSegment:
    segment_id: str
    cue_id: str
    source_start_ms: int
    source_end_ms: int
    scene_id: str = ""
    shot_id: str = ""
    beat_id: str = ""
    event_ids: tuple[str, ...] = ()
    role: str = ""
    program_start_ms: int = 0
    program_end_ms: int = 0


@dataclass(frozen=True, slots=True)
class EdlDocument:
    segments: tuple[EdlSegment, ...]


@dataclass(frozen=True, slots=True)
class SpanEdlSegment:
    segment_id: str
    span_id: str
    source_start_ms: int
    source_end_ms: int
    program_start_ms: int
    program_end_ms: int
    range_id: str
    scene_id: str
    beat_id: str
    shot_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    short_action_exception: bool


@dataclass(frozen=True, slots=True)
class SpanEdlDocument:
    segments: tuple[SpanEdlSegment, ...]

    def __post_init__(self) -> None:
        if not self.segments:
            raise MvpError("span EDL requires segments")


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


@dataclass(frozen=True, slots=True)
class SpanSemanticReview:
    span_id: str
    supported: bool
    finding_codes: tuple[str, ...]
    evidence_anchor_ids: tuple[str, ...]
    note: str

    def __post_init__(self) -> None:
        _non_empty(self.span_id, "semantic review span_id")
        if not self.evidence_anchor_ids:
            raise MvpError("semantic review requires anchor evidence")
        if not self.supported and not self.finding_codes:
            raise MvpError("unsupported span requires a finding code")
        _non_empty(self.note, "semantic review note")


@dataclass(frozen=True, slots=True)
class CodexSemanticReview:
    owner: str
    spans: tuple[SpanSemanticReview, ...]

    def __post_init__(self) -> None:
        _non_empty(self.owner, "semantic review owner")
        if not self.spans:
            raise MvpError("semantic review requires spans")


@dataclass(frozen=True, slots=True)
class EngineAuditReport:
    passed: bool
    coverage_ratio: str
    findings: tuple[AuditFinding, ...]
