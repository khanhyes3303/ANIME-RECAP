from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import MvpError
from .jsonio import load_json


def _non_empty(value: str, field: str) -> None:
    if not value.strip():
        raise MvpError(f"{field} must not be empty")


def _positive_interval(start_ms: int, end_ms: int, field: str) -> None:
    if start_ms < 0 or end_ms <= start_ms:
        raise MvpError(f"{field} interval is invalid")


def _sha256(value: str, field: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise MvpError(f"{field} must be a lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class EditorialPolicy:
    minimum_clip_ms: int = 500
    minimum_omitted_gap_ms: int = 500
    minimum_playback_rate: float = 0.80
    maximum_playback_rate: float = 1.30
    forbidden_before_ms: int = 0
    target_minimum_ms: int = 420_000
    target_maximum_ms: int = 720_000
    fixed_keep_ms: int | None = None
    fixed_skip_ms: int | None = None

    def __post_init__(self) -> None:
        if self.fixed_keep_ms is not None or self.fixed_skip_ms is not None:
            raise MvpError("fixed keep/skip formulas are forbidden")
        if self.minimum_clip_ms <= 0 or self.minimum_omitted_gap_ms <= 0:
            raise MvpError("clip and omitted-gap limits must be positive")
        if not 0 < self.minimum_playback_rate <= self.maximum_playback_rate:
            raise MvpError("playback-rate policy is invalid")
        if self.forbidden_before_ms < 0:
            raise MvpError("forbidden-before timestamp must not be negative")
        if not 0 < self.target_minimum_ms <= self.target_maximum_ms:
            raise MvpError("target duration policy is invalid")


@dataclass(frozen=True, slots=True)
class Situation:
    situation_id: str
    source_start_ms: int
    source_end_ms: int
    story_role: str
    characters: tuple[str, ...]
    setup: str
    new_information: tuple[str, ...]
    turning_points: tuple[str, ...]
    outcome: str
    transcript_refs: tuple[str, ...]
    frame_refs: tuple[str, ...]
    previous_situation_id: str | None
    next_situation_id: str | None
    confidence: float

    def __post_init__(self) -> None:
        _non_empty(self.situation_id, "situation_id")
        _positive_interval(self.source_start_ms, self.source_end_ms, "situation")
        if self.story_role not in {"MAIN_PLOT", "SUPPORTING_PLOT"}:
            raise MvpError("situation story_role is invalid")
        if not self.characters:
            raise MvpError("situation requires characters")
        _non_empty(self.setup, "situation setup")
        _non_empty(self.outcome, "situation outcome")
        if not self.transcript_refs or not self.frame_refs:
            raise MvpError("situation requires transcript and frame evidence")
        if not 0 <= self.confidence <= 1:
            raise MvpError("situation confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class SituationDocument:
    owner: str
    policy_version: str
    situations: tuple[Situation, ...]

    def __post_init__(self) -> None:
        if self.owner != "LOCAL_EDITOR":
            raise MvpError("situation owner must be LOCAL_EDITOR")
        _non_empty(self.policy_version, "situation policy_version")
        if not self.situations:
            raise MvpError("situation document requires situations")


@dataclass(frozen=True, slots=True)
class EvidenceRange:
    range_id: str
    situation_id: str
    source_start_ms: int
    source_end_ms: int
    shot_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    transcript_refs: tuple[str, ...]
    frame_refs: tuple[str, ...]
    story_fact: str

    def __post_init__(self) -> None:
        _non_empty(self.range_id, "evidence range_id")
        _non_empty(self.situation_id, "evidence situation_id")
        _positive_interval(self.source_start_ms, self.source_end_ms, "evidence range")
        if not self.shot_ids or not self.event_ids:
            raise MvpError("evidence range requires shot and event IDs")
        if not self.transcript_refs and not self.frame_refs:
            raise MvpError("evidence range requires transcript or frame evidence")
        _non_empty(self.story_fact, "evidence story_fact")


@dataclass(frozen=True, slots=True)
class NarrationUnit:
    unit_id: str
    situation_id: str
    factual_claims: tuple[str, ...]
    narration_text: str
    bridge_from_previous: str
    bridge_to_next: str
    evidence_ranges: tuple[EvidenceRange, ...]
    status: str

    def __post_init__(self) -> None:
        _non_empty(self.unit_id, "narration unit_id")
        _non_empty(self.situation_id, "narration situation_id")
        if not self.factual_claims:
            raise MvpError("narration unit requires factual claims")
        _non_empty(self.narration_text, "narration text")
        if not self.evidence_ranges:
            raise MvpError("narration unit requires evidence ranges")
        if self.status not in {"DRAFT", "LOCKED", "NEEDS_REPAIR"}:
            raise MvpError("narration unit status is invalid")


@dataclass(frozen=True, slots=True)
class NarrationPlan:
    owner: str
    policy_version: str
    units: tuple[NarrationUnit, ...]

    def __post_init__(self) -> None:
        if self.owner != "LOCAL_EDITOR":
            raise MvpError("narration owner must be LOCAL_EDITOR")
        _non_empty(self.policy_version, "narration policy_version")
        if not self.units:
            raise MvpError("narration plan requires units")


@dataclass(frozen=True, slots=True)
class SituationTts:
    unit_id: str
    mp3_path: str
    wav_path: str
    duration_ms: int
    cache_key: str

    def __post_init__(self) -> None:
        _non_empty(self.unit_id, "TTS unit_id")
        _non_empty(self.mp3_path, "TTS MP3 path")
        _non_empty(self.wav_path, "TTS WAV path")
        if self.duration_ms <= 0:
            raise MvpError("TTS duration must be positive")
        _sha256(self.cache_key, "TTS cache key")


@dataclass(frozen=True, slots=True)
class SituationTtsManifest:
    units: tuple[SituationTts, ...]
    narration_wav_path: str
    provider: str
    voice_id: str
    policy_version: str
    cache_hits: int
    cache_misses: int
    total_duration_ms: int

    def __post_init__(self) -> None:
        if not self.units:
            raise MvpError("situation TTS manifest requires units")
        _non_empty(self.narration_wav_path, "narration WAV path")
        _non_empty(self.provider, "TTS provider")
        _non_empty(self.voice_id, "TTS voice_id")
        _non_empty(self.policy_version, "TTS policy_version")
        if self.cache_hits < 0 or self.cache_misses < 0:
            raise MvpError("TTS cache counters cannot be negative")
        if self.total_duration_ms != sum(unit.duration_ms for unit in self.units):
            raise MvpError("TTS total duration does not match unit durations")


@dataclass(frozen=True, slots=True)
class SemanticUnitReview:
    unit_id: str
    supported: bool
    finding_codes: tuple[str, ...]
    transcript_refs: tuple[str, ...]
    source_frame_refs: tuple[str, ...]
    program_frame_refs: tuple[str, ...]
    note: str

    def __post_init__(self) -> None:
        _non_empty(self.unit_id, "semantic unit_id")
        if not self.transcript_refs or not self.source_frame_refs or not self.program_frame_refs:
            raise MvpError("semantic review requires transcript, source, and program evidence")
        if self.supported and self.finding_codes:
            raise MvpError("supported semantic review cannot contain findings")
        if not self.supported and not self.finding_codes:
            raise MvpError("unsupported semantic review requires findings")
        _non_empty(self.note, "semantic review note")


@dataclass(frozen=True, slots=True)
class SemanticReviewDocument:
    owner: str
    units: tuple[SemanticUnitReview, ...]

    def __post_init__(self) -> None:
        if self.owner != "LOCAL_SEMANTIC_AUDITOR":
            raise MvpError("semantic review owner must be LOCAL_SEMANTIC_AUDITOR")
        if not self.units:
            raise MvpError("semantic review requires units")


def load_situations(path: Path) -> SituationDocument:
    return load_json(path, SituationDocument)


def load_narration_plan(path: Path) -> NarrationPlan:
    return load_json(path, NarrationPlan)
