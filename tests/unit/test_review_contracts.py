from __future__ import annotations

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.review_contracts import (
    BoundaryVerdict,
    CueSemanticVerdict,
    ProxyAuditDocument,
    SituationAuditDocument,
)


def valid_cue_review() -> CueSemanticVerdict:
    return CueSemanticVerdict(
        cue_id="cue-001",
        situation_id="situation-001",
        verdict="MATCH",
        observed_visual="Jiro gap Rago.",
        narration_meaning="Jiro tim thay Rago.",
        transcript_refs=("segment-001",),
        frame_refs=("frame-001",),
        visual_only=False,
        voice_before_visual=False,
        mixed_semantics=False,
        finding_codes=(),
        note="Khop.",
    )


def valid_boundary_review(boundary: str) -> BoundaryVerdict:
    return BoundaryVerdict(
        boundary=boundary,
        verdict="CLEAN",
        frame_refs=(f"{boundary.casefold()}-frame-001",),
        transcript_refs=(),
        finding_codes=(),
        note="Sach.",
    )


def test_situation_audit_requires_one_evidence_backed_verdict_per_cue() -> None:
    with pytest.raises(MvpError, match="VERIFIER_EVIDENCE_REQUIRED"):
        CueSemanticVerdict(
            cue_id="cue-001",
            situation_id="situation-001",
            verdict="MATCH",
            observed_visual="Jiro gap Rago.",
            narration_meaning="Jiro tim thay Rago.",
            transcript_refs=(),
            frame_refs=(),
            visual_only=False,
            voice_before_visual=False,
            mixed_semantics=False,
            finding_codes=(),
            note="Khop.",
        )


def test_producer_and_verifier_contexts_must_differ() -> None:
    with pytest.raises(MvpError, match="VERIFIER_CONTEXT_NOT_INDEPENDENT"):
        SituationAuditDocument(
            editor="ANTIGRAVITY_VERIFIER",
            policy_version="situation-v3",
            situation_id="situation-001",
            producer_task_id="situation-001-revision-001",
            producer_context_id="context-a",
            verifier_context_id="context-a",
            cue_reviews=(valid_cue_review(),),
        )


def test_situation_audit_rejects_cues_from_other_situations() -> None:
    with pytest.raises(MvpError, match="VERIFIER_SITUATION_SCOPE_INVALID"):
        SituationAuditDocument(
            editor="ANTIGRAVITY_VERIFIER",
            policy_version="situation-v3",
            situation_id="situation-001",
            producer_task_id="situation-001-revision-001",
            producer_context_id="producer-context-a",
            verifier_context_id="verifier-context-b",
            cue_reviews=(
                valid_cue_review(),
                CueSemanticVerdict(
                    cue_id="cue-002",
                    situation_id="situation-002",
                    verdict="MISMATCH",
                    observed_visual="Rago roi di.",
                    narration_meaning="Rago van dang o lai.",
                    transcript_refs=("segment-002",),
                    frame_refs=(),
                    visual_only=False,
                    voice_before_visual=False,
                    mixed_semantics=False,
                    finding_codes=("SCENE_MISMATCH",),
                    note="Khac tinh huong.",
                ),
            ),
        )


@pytest.mark.parametrize(
    ("boundary_reviews", "error_code"),
    (
        ((), "VERIFIER_BOUNDARY_COVERAGE_INVALID"),
        ((valid_boundary_review("START"),), "VERIFIER_BOUNDARY_COVERAGE_INVALID"),
        (
            (valid_boundary_review("START"), valid_boundary_review("START")),
            "VERIFIER_BOUNDARY_COVERAGE_INVALID",
        ),
    ),
)
def test_proxy_audit_requires_exact_start_and_end_boundaries(
    boundary_reviews: tuple[BoundaryVerdict, ...],
    error_code: str,
) -> None:
    with pytest.raises(MvpError, match=error_code):
        ProxyAuditDocument(
            editor="ANTIGRAVITY_VERIFIER",
            policy_version="proxy-v1",
            producer_context_id="producer-context-a",
            verifier_context_id="verifier-context-b",
            cue_reviews=(valid_cue_review(),),
            boundary_reviews=boundary_reviews,
        )
