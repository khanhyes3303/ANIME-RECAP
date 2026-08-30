from __future__ import annotations

from dataclasses import replace

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import Event, Shot, SourceRegionAnnotation, TruthDocument
from anime_review_mvp.situation_validation import (
    coherence_findings,
    validate_causal_chains,
    validate_keep_skip,
    validate_narration_plan,
    validate_semantic_range,
    validate_situations,
)
from anime_review_mvp.situations import (
    EditorialPolicy,
    EvidenceRange,
    NarrationClaim,
    NarrationCue,
    NarrationPlan,
    NarrationUnit,
    SemanticShotUse,
    Situation,
    SituationDocument,
)

POLICY = EditorialPolicy(
    minimum_clip_ms=500,
    minimum_omitted_gap_ms=500,
    forbidden_before_ms=1_000,
    target_minimum_ms=1_000,
    target_maximum_ms=20_000,
)
SHOTS = (
    Shot("shot-001", 1_000, 4_000),
    Shot("shot-002", 4_000, 5_000),
    Shot("shot-003", 5_000, 9_000),
    Shot("shot-004", 9_000, 12_000),
)


def _truth(*, excluded: bool = False) -> TruthDocument:
    regions = (
        SourceRegionAnnotation(
            "region-001", 0, 1_000, "OPENING", "EXCLUDE", "Opening sequence"
        ),
    ) if excluded else ()
    return TruthDocument(
        events=(
            Event(
                "event-001",
                1_000,
                12_000,
                ("Jiro",),
                "Jiro is attacked and fights back.",
                "MAIN",
                1.0,
            ),
        ),
        source_regions=regions,
        source_region_scan_complete=True,
    )


def _situation(**changes: object) -> Situation:
    base = Situation(
        situation_id="situation-001",
        source_start_ms=1_000,
        source_end_ms=12_000,
        story_role="MAIN_PLOT",
        characters=("Jiro",),
        setup="Băng nhóm chặn Jiro.",
        new_information=("Bọn chúng chủ động gây sự.",),
        turning_points=("Jiro phản công.",),
        outcome="Jiro hạ cả băng.",
        transcript_refs=("transcript-001",),
        frame_refs=("frame-001",),
        previous_situation_id=None,
        next_situation_id=None,
        confidence=1.0,
        action_role="MAIN_ACTION",
        future_payoff="",
    )
    return replace(base, **changes)


def _range(
    range_id: str,
    start_ms: int,
    end_ms: int,
    shot_id: str,
) -> EvidenceRange:
    return EvidenceRange(
        range_id=range_id,
        situation_id="situation-001",
        source_start_ms=start_ms,
        source_end_ms=end_ms,
        shot_ids=(shot_id,),
        event_ids=("event-001",),
        transcript_refs=("transcript-001",),
        frame_refs=(f"frame-{range_id}",),
        story_fact="Diễn biến làm thay đổi tình huống.",
    )


def _plan(*ranges: EvidenceRange) -> NarrationPlan:
    return NarrationPlan(
        owner="LOCAL_EDITOR",
        policy_version="situation-v1",
        units=(
            NarrationUnit(
                unit_id="unit-001",
                situation_id="situation-001",
                factual_claims=("Jiro bị tấn công rồi phản công.",),
                narration_text="Đám này vừa lao vào thì Jiro cho ăn hành luôn.",
                bridge_from_previous="",
                bridge_to_next="",
                evidence_ranges=ranges,
                status="LOCKED",
            ),
        ),
    )


def _document(situation: Situation | None = None) -> SituationDocument:
    return SituationDocument("LOCAL_EDITOR", "situation-v1", (situation or _situation(),))


def test_rejects_decorative_action_without_new_story_information() -> None:
    situation = _situation(
        action_role="DECORATIVE",
        new_information=(),
        turning_points=(),
        outcome="Không có gì thay đổi.",
    )

    with pytest.raises(MvpError, match="no review value"):
        validate_situations(_document(situation), _truth(), SHOTS, source_duration_ms=20_000)


def test_supporting_plot_requires_future_payoff() -> None:
    situation = _situation(story_role="SUPPORTING_PLOT", future_payoff="")

    with pytest.raises(MvpError, match="future payoff"):
        validate_situations(_document(situation), _truth(), SHOTS, source_duration_ms=20_000)


def test_rejects_kept_range_in_confirmed_opening() -> None:
    plan = _plan(_range("range-001", 500, 4_000, "shot-001"))

    with pytest.raises(MvpError, match="excluded source region|forbidden"):
        validate_narration_plan(
            plan, _document(), _truth(excluded=True), SHOTS, POLICY, 20_000
        )


def test_requires_real_omitted_gap_between_kept_ranges() -> None:
    plan = _plan(
        _range("range-001", 1_000, 4_000, "shot-001"),
        _range("range-002", 4_200, 9_000, "shot-003"),
    )

    with pytest.raises(MvpError, match="omitted gap.*500"):
        validate_keep_skip(plan, source_duration_ms=20_000, policy=POLICY)


def test_requires_omitted_tail_after_final_kept_range() -> None:
    plan = _plan(_range("range-001", 1_000, 19_800, "shot-001"))

    with pytest.raises(MvpError, match="source tail"):
        validate_keep_skip(plan, source_duration_ms=20_000, policy=POLICY)


def test_rejects_micro_clip() -> None:
    plan = _plan(_range("range-001", 1_000, 1_300, "shot-001"))

    with pytest.raises(MvpError, match="at least 500 ms"):
        validate_keep_skip(plan, source_duration_ms=20_000, policy=POLICY)


def test_valid_plan_passes_all_checks() -> None:
    plan = _plan(
        _range("range-001", 1_000, 4_000, "shot-001"),
        _range("range-002", 5_000, 9_000, "shot-003"),
    )

    validate_situations(_document(), _truth(), SHOTS, source_duration_ms=20_000)
    validate_narration_plan(plan, _document(), _truth(), SHOTS, POLICY, 20_000)


def test_long_shot_may_be_trimmed_inside_declared_shot() -> None:
    plan = _plan(_range("range-001", 1_500, 3_500, "shot-001"))

    validate_narration_plan(plan, _document(), _truth(), SHOTS, POLICY, 20_000)


def test_trimmed_range_rejects_wrong_shot_id() -> None:
    plan = _plan(_range("range-001", 1_500, 3_500, "shot-003"))

    with pytest.raises(MvpError, match="shot IDs"):
        validate_narration_plan(plan, _document(), _truth(), SHOTS, POLICY, 20_000)


def test_v2_situation_requires_complete_causal_chain() -> None:
    with pytest.raises(MvpError, match="CAUSAL_CHAIN_INCOMPLETE"):
        SituationDocument(
            "LOCAL_EDITOR", "situation-v2",
            (_situation(cause_or_goal="", audience_summary=""),),
        )


def test_complete_v2_causal_chain_is_accepted() -> None:
    document = SituationDocument(
        "LOCAL_EDITOR", "situation-v2",
        (_situation(
            cause_or_goal="Jiro phải thoát khỏi đám côn đồ.",
            audience_summary="Jiro bị chặn đường, phản công rồi thoát nạn.",
        ),),
    )
    validate_causal_chains(document)


def test_v2_validation_uses_scoped_evidence_without_legacy_truth() -> None:
    situation = _situation(
        cause_or_goal="Jiro cần được người thân thấu hiểu.",
        audience_summary="Jiro bị xa lánh rồi về nhà tâm sự.",
    )
    document = SituationDocument("LOCAL_EDITOR", "situation-v2", (situation,))
    source_range = replace(
        _range("range-001", 1_000, 4_000, "shot-001"),
        semantic_event_id="jiro-confession",
        action_phase="REACTION",
        story_purpose="Jiro bộc lộ sự cô độc.",
        shot_uses=(
            SemanticShotUse(
                "shot-001",
                "jiro-confession",
                "REACTION",
                "Jiro bộc lộ sự cô độc.",
            ),
        ),
    )
    cue = NarrationCue(
        "cue-001",
        "situation-001",
        "Jiro bị xa lánh rồi về nhà tâm sự.",
        ("claim-001",),
        1_500,
        "REVEAL",
        ("transcript-001",),
        ("frame-range-001",),
        ("shot-001",),
        ("Jiro",),
        (),
        (),
        (),
    )
    unit = replace(_plan(source_range).units[0], cues=(cue,))
    plan = NarrationPlan(
        "LOCAL_EDITOR",
        "situation-v2",
        (unit,),
        (NarrationClaim("claim-001", "Jiro bị xa lánh.", ("event-001",)),),
    )

    validate_situations(document, None, SHOTS, source_duration_ms=20_000)
    validate_narration_plan(plan, document, None, SHOTS, POLICY, 20_000)


def test_range_mixing_shot_meanings_is_rejected_regardless_of_duration() -> None:
    source_range = EvidenceRange(
        "range-mixed", "situation-001", 10_000, 18_000,
        ("shot-001", "shot-002", "shot-003"), ("event-001",),
        ("transcript-001",), ("frame-001",), "Jiro ra đòn.",
        "fight-hit", "ACTION", "Jiro ra đòn.",
        (
            SemanticShotUse("shot-001", "fight-approach", "APPROACH", "Jiro áp sát."),
            SemanticShotUse("shot-002", "fight-hit", "ACTION", "Jiro ra đòn."),
            SemanticShotUse("shot-003", "fight-reaction", "REACTION", "Địch hoảng sợ."),
        ),
    )
    with pytest.raises(MvpError, match="SEMANTIC_RANGE_MIXED.*shot-001.*shot-003"):
        validate_semantic_range(source_range)


def test_four_second_range_with_one_meaning_is_accepted() -> None:
    source_range = EvidenceRange(
        "range-clean", "situation-001", 12_000, 16_000, ("shot-002",),
        ("event-001",), ("transcript-001",), ("frame-001",), "Jiro ra đòn.",
        "fight-hit", "ACTION", "Jiro ra đòn.",
        (SemanticShotUse("shot-002", "fight-hit", "ACTION", "Jiro ra đòn."),),
    )
    validate_semantic_range(source_range)


def test_repeated_filler_bridge_is_reported() -> None:
    base = _plan(_range("range-001", 1_000, 4_000, "shot-001"))
    units = tuple(
        replace(
            base.units[0], unit_id=f"unit-{index}",
            bridge_from_previous="Tiếp đó rồi mọi chuyện lại tiếp diễn.",
            bridge_to_next="Tiếp đó rồi mọi chuyện lại tiếp diễn.",
        )
        for index in range(4)
    )
    plan = NarrationPlan("LOCAL_EDITOR", "situation-v1", units)
    codes = {finding.code for finding in coherence_findings(plan, _document())}
    assert "REPETITIVE_FILLER_BRIDGE" in codes
