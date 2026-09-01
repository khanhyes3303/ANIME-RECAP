from __future__ import annotations

from dataclasses import dataclass, field
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
    action_role: str = "MAIN_ACTION"
    future_payoff: str = ""
    cause_or_goal: str = field(default="", metadata={"json_optional": True})
    audience_summary: str = field(default="", metadata={"json_optional": True})

    def __post_init__(self) -> None:
        _non_empty(self.situation_id, "situation_id")
        _positive_interval(self.source_start_ms, self.source_end_ms, "situation")
        if self.story_role not in {"MAIN_PLOT", "SUPPORTING_PLOT"}:
            raise MvpError("situation story_role is invalid")
        if self.action_role not in {"MAIN_ACTION", "SUPPORTING_ACTION", "DECORATIVE"}:
            raise MvpError("situation action_role is invalid")
        if not self.characters:
            raise MvpError("situation requires characters")
        _non_empty(self.setup, "situation setup")
        _non_empty(self.outcome, "situation outcome")
        if not self.frame_refs:
            raise MvpError("situation requires frame evidence")
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
        if self.policy_version == "situation-v2":
            for situation in self.situations:
                if not situation.cause_or_goal.strip() or not situation.audience_summary.strip():
                    raise MvpError("CAUSAL_CHAIN_INCOMPLETE: cause_or_goal or audience_summary")


_ACTION_PHASES = {"SETUP", "CAUSE", "APPROACH", "ACTION", "OUTCOME", "REACTION", "BRIDGE"}


@dataclass(frozen=True, slots=True)
class SemanticShotUse:
    shot_id: str
    semantic_event_id: str
    action_phase: str
    story_purpose: str

    def __post_init__(self) -> None:
        _non_empty(self.shot_id, "semantic shot_id")
        _non_empty(self.semantic_event_id, "semantic event_id")
        if self.action_phase not in _ACTION_PHASES:
            raise MvpError("semantic action_phase is invalid")
        _non_empty(self.story_purpose, "semantic story_purpose")


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
    semantic_event_id: str = field(default="", metadata={"json_optional": True})
    action_phase: str = field(default="", metadata={"json_optional": True})
    story_purpose: str = field(default="", metadata={"json_optional": True})
    shot_uses: tuple[SemanticShotUse, ...] = field(default=(), metadata={"json_optional": True})

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
class NarrationClaim:
    claim_id: str
    text: str
    event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _non_empty(self.claim_id, "claim_id")
        _non_empty(self.text, "claim text")
        if not self.event_ids:
            raise MvpError("narration claim requires event IDs")


@dataclass(frozen=True, slots=True)
class NarrationCue:
    cue_id: str
    situation_id: str
    text: str
    claim_ids: tuple[str, ...]
    visual_anchor_source_ms: int
    anchor_kind: str
    transcript_refs: tuple[str, ...]
    frame_refs: tuple[str, ...]
    shot_ids: tuple[str, ...]
    introduces_characters: tuple[str, ...]
    mentions_characters: tuple[str, ...]
    introduces_terms: tuple[str, ...]
    mentions_terms: tuple[str, ...]
    visual_preroll_ms: int = 200
    visual_postroll_ms: int = 100

    def __post_init__(self) -> None:
        _non_empty(self.cue_id, "cue_id")
        _non_empty(self.situation_id, "cue situation_id")
        _non_empty(self.text, "cue text")
        if not self.claim_ids:
            raise MvpError("narration cue requires claims")
        if self.visual_anchor_source_ms < 0:
            raise MvpError("visual anchor timestamp must not be negative")
        if self.anchor_kind not in {
            "SETUP",
            "CHARACTER_INTRO",
            "CAUSE",
            "ACTION",
            "REVEAL",
            "OUTCOME",
            "BRIDGE",
        }:
            raise MvpError("visual anchor kind is invalid")
        if not self.frame_refs or not self.shot_ids:
            raise MvpError("narration cue requires frame and shot evidence")
        if not 100 <= self.visual_preroll_ms <= 1_200:
            raise MvpError("visual preroll is invalid")
        if not 0 <= self.visual_postroll_ms <= 1_200:
            raise MvpError("visual postroll is invalid")
        for values in (
            self.introduces_characters,
            self.mentions_characters,
            self.introduces_terms,
            self.mentions_terms,
        ):
            if len(values) != len(set(values)):
                raise MvpError("cue introductions and mentions must be unique")


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
    cues: tuple[NarrationCue, ...] = field(default=(), metadata={"json_optional": True})

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


def cue_evidence_range(unit: NarrationUnit, cue: NarrationCue) -> EvidenceRange:
    """Resolve the one accepted range that proves a cue's exact visual claim."""
    candidates = tuple(
        evidence
        for evidence in unit.evidence_ranges
        if evidence.source_start_ms <= cue.visual_anchor_source_ms < evidence.source_end_ms
        and set(cue.shot_ids) <= set(evidence.shot_ids)
        and set(cue.frame_refs) <= set(evidence.frame_refs)
        and bool(cue.transcript_refs) == bool(evidence.transcript_refs)
        and set(cue.transcript_refs) <= set(evidence.transcript_refs)
    )
    if not cue.transcript_refs and any(
        evidence.source_start_ms <= cue.visual_anchor_source_ms < evidence.source_end_ms
        and set(cue.shot_ids) <= set(evidence.shot_ids)
        and set(cue.frame_refs) <= set(evidence.frame_refs)
        and evidence.transcript_refs
        for evidence in unit.evidence_ranges
    ):
        raise MvpError(f"CUE_TRANSCRIPT_GROUNDING_REQUIRED: {cue.cue_id}")
    if len(candidates) != 1:
        raise MvpError(
            f"CUE_EVIDENCE_RANGE_INVALID: {cue.cue_id} resolves to {len(candidates)} ranges"
        )
    return candidates[0]


@dataclass(frozen=True, slots=True)
class NarrationPlan:
    owner: str
    policy_version: str
    units: tuple[NarrationUnit, ...]
    claims: tuple[NarrationClaim, ...] = field(default=(), metadata={"json_optional": True})

    def __post_init__(self) -> None:
        if self.owner != "LOCAL_EDITOR":
            raise MvpError("narration owner must be LOCAL_EDITOR")
        _non_empty(self.policy_version, "narration policy_version")
        if not self.units:
            raise MvpError("narration plan requires units")
        if self.policy_version == "situation-v2":
            self._validate_v2()

    def _validate_v2(self) -> None:
        if not self.claims or any(not unit.cues for unit in self.units):
            raise MvpError("situation-v2 requires claims and cues")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise MvpError("narration claim IDs must be unique")
        known_claims = set(claim_ids)
        cue_ids = [cue.cue_id for unit in self.units for cue in unit.cues]
        if len(cue_ids) != len(set(cue_ids)):
            raise MvpError("narration cue IDs must be unique")
        for unit in self.units:
            if any(cue.situation_id != unit.situation_id for cue in unit.cues):
                raise MvpError("cue situation does not match narration unit")
            for cue in unit.cues:
                if any(claim_id not in known_claims for claim_id in cue.claim_ids):
                    raise MvpError("cue claim does not resolve exactly once")
                cue_evidence_range(unit, cue)
            for evidence in unit.evidence_ranges:
                self._validate_semantic_range(evidence)

    @staticmethod
    def _validate_semantic_range(evidence: EvidenceRange) -> None:
        if (
            not evidence.semantic_event_id.strip()
            or evidence.action_phase not in _ACTION_PHASES
            or not evidence.story_purpose.strip()
            or not evidence.shot_uses
        ):
            raise MvpError("situation-v2 requires semantic range labels")
        uses_match = all(
            use.semantic_event_id == evidence.semantic_event_id
            and use.action_phase == evidence.action_phase
            and use.story_purpose == evidence.story_purpose
            for use in evidence.shot_uses
        )
        if not uses_match or {use.shot_id for use in evidence.shot_uses} != set(evidence.shot_ids):
            raise MvpError("SEMANTIC_RANGE_MIXED")


@dataclass(frozen=True, slots=True)
class CueTts:
    cue_id: str
    unit_id: str
    wav_path: str
    mp3_path: str
    duration_ms: int
    cache_key: str

    def __post_init__(self) -> None:
        _non_empty(self.cue_id, "TTS cue_id")
        _non_empty(self.unit_id, "TTS unit_id")
        _non_empty(self.wav_path, "TTS WAV path")
        _non_empty(self.mp3_path, "TTS MP3 path")
        if self.duration_ms <= 0:
            raise MvpError("TTS cue duration must be positive")
        _sha256(self.cache_key, "TTS cue cache key")


@dataclass(frozen=True, slots=True)
class CueTtsManifest:
    cues: tuple[CueTts, ...]
    provider: str
    voice_id: str
    policy_version: str
    cache_hits: int
    cache_misses: int

    def __post_init__(self) -> None:
        if not self.cues:
            raise MvpError("cue TTS manifest requires cues")
        _non_empty(self.provider, "cue TTS provider")
        _non_empty(self.voice_id, "cue TTS voice_id")
        _non_empty(self.policy_version, "cue TTS policy_version")
        if self.cache_hits < 0 or self.cache_misses < 0:
            raise MvpError("cue TTS cache counters cannot be negative")
        if self.cache_hits + self.cache_misses != len(self.cues):
            raise MvpError("cue TTS cache counters do not match cues")


@dataclass(frozen=True, slots=True)
class CharacterContext:
    name: str
    viewer_role: str
    introduced_cue_id: str

    def __post_init__(self) -> None:
        _non_empty(self.name, "character name")
        _non_empty(self.viewer_role, "character viewer_role")
        _non_empty(self.introduced_cue_id, "character introduced_cue_id")


@dataclass(frozen=True, slots=True)
class TermContext:
    term: str
    plain_explanation: str
    introduced_cue_id: str

    def __post_init__(self) -> None:
        _non_empty(self.term, "term")
        _non_empty(self.plain_explanation, "term plain_explanation")
        _non_empty(self.introduced_cue_id, "term introduced_cue_id")


@dataclass(frozen=True, slots=True)
class StoryContext:
    characters: tuple[CharacterContext, ...]
    terms: tuple[TermContext, ...]
    unresolved_threads: tuple[str, ...]
    last_outcome: str


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
