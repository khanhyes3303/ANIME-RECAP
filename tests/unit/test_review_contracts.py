from __future__ import annotations

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.review_contracts import CueSemanticVerdict, SituationAuditDocument


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
            producer_task_id="situation-001-revision-001",
            producer_context_id="context-a",
            verifier_context_id="context-a",
            cue_reviews=(valid_cue_review(),),
        )

