from __future__ import annotations

from dataclasses import dataclass, field

from .errors import MvpError

_SEMANTIC_VERDICTS = {"MATCH", "MISMATCH", "INSUFFICIENT_EVIDENCE"}
_BOUNDARY_NAMES = {"START", "END"}
_BOUNDARY_VERDICTS = {"CLEAN", "LEAKED_EXCLUDED_CONTENT", "INSUFFICIENT_EVIDENCE"}


@dataclass(frozen=True, slots=True)
class CueSemanticVerdict:
    cue_id: str
    situation_id: str
    verdict: str
    observed_visual: str
    narration_meaning: str
    transcript_refs: tuple[str, ...]
    frame_refs: tuple[str, ...]
    visual_only: bool
    voice_before_visual: bool
    mixed_semantics: bool
    finding_codes: tuple[str, ...]
    note: str

    def __post_init__(self) -> None:
        if not self.cue_id.strip() or not self.situation_id.strip():
            raise MvpError("VERIFIER_VERDICT_INVALID")
        if self.verdict not in _SEMANTIC_VERDICTS:
            raise MvpError("VERIFIER_VERDICT_INVALID")
        if not self.transcript_refs and not self.frame_refs:
            raise MvpError("VERIFIER_EVIDENCE_REQUIRED")
        if not self.observed_visual.strip() or not self.narration_meaning.strip():
            raise MvpError("VERIFIER_VERDICT_INVALID")
        if not self.note.strip():
            raise MvpError("VERIFIER_VERDICT_INVALID")


@dataclass(frozen=True, slots=True)
class BoundaryVerdict:
    boundary: str
    verdict: str
    frame_refs: tuple[str, ...]
    transcript_refs: tuple[str, ...]
    finding_codes: tuple[str, ...]
    note: str

    def __post_init__(self) -> None:
        if self.boundary not in _BOUNDARY_NAMES or self.verdict not in _BOUNDARY_VERDICTS:
            raise MvpError("VERIFIER_BOUNDARY_INVALID")
        if not self.frame_refs and not self.transcript_refs:
            raise MvpError("VERIFIER_EVIDENCE_REQUIRED")
        if not self.note.strip():
            raise MvpError("VERIFIER_BOUNDARY_INVALID")


@dataclass(frozen=True, slots=True)
class LoudnessReport:
    integrated_lufs: float
    true_peak_dbtp: float
    loudness_range_lu: float
    normalized_audio_path: str
    normalized_audio_sha256: str = field(default="", metadata={"json_optional": True})

    def __post_init__(self) -> None:
        if not self.normalized_audio_path.strip():
            raise MvpError("LOUDNESS_REPORT_INVALID")


def _validate_context_independence(
    producer_context_id: str,
    verifier_context_id: str,
) -> None:
    if not producer_context_id.strip() or not verifier_context_id.strip():
        raise MvpError("VERIFIER_CONTEXT_INVALID")
    if producer_context_id == verifier_context_id:
        raise MvpError("VERIFIER_CONTEXT_NOT_INDEPENDENT")


def _validate_cue_reviews(cue_reviews: tuple[CueSemanticVerdict, ...]) -> None:
    if not cue_reviews:
        raise MvpError("VERIFIER_AUDIT_INVALID")
    cue_ids = {review.cue_id for review in cue_reviews}
    if len(cue_ids) != len(cue_reviews):
        raise MvpError("VERIFIER_CUE_DUPLICATE")


@dataclass(frozen=True, slots=True)
class SituationAuditDocument:
    editor: str
    policy_version: str
    situation_id: str
    producer_task_id: str
    producer_context_id: str
    verifier_context_id: str
    cue_reviews: tuple[CueSemanticVerdict, ...]

    def __post_init__(self) -> None:
        if not self.editor.strip() or not self.policy_version.strip():
            raise MvpError("VERIFIER_AUDIT_INVALID")
        if not self.situation_id.strip() or not self.producer_task_id.strip():
            raise MvpError("VERIFIER_AUDIT_INVALID")
        _validate_context_independence(
            self.producer_context_id,
            self.verifier_context_id,
        )
        _validate_cue_reviews(self.cue_reviews)
        if any(review.situation_id != self.situation_id for review in self.cue_reviews):
            raise MvpError("VERIFIER_SITUATION_SCOPE_INVALID")


@dataclass(frozen=True, slots=True)
class ProxyAuditDocument:
    editor: str
    policy_version: str
    producer_context_id: str
    verifier_context_id: str
    cue_reviews: tuple[CueSemanticVerdict, ...]
    boundary_reviews: tuple[BoundaryVerdict, ...]

    def __post_init__(self) -> None:
        if not self.editor.strip() or not self.policy_version.strip():
            raise MvpError("VERIFIER_AUDIT_INVALID")
        _validate_context_independence(
            self.producer_context_id,
            self.verifier_context_id,
        )
        _validate_cue_reviews(self.cue_reviews)
        if len(self.boundary_reviews) != 2:
            raise MvpError("VERIFIER_BOUNDARY_COVERAGE_INVALID")
        boundaries = tuple(review.boundary for review in self.boundary_reviews)
        if boundaries.count("START") != 1 or boundaries.count("END") != 1:
            raise MvpError("VERIFIER_BOUNDARY_COVERAGE_INVALID")
