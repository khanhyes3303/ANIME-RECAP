from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.situations import (
    EditorialPolicy,
    EvidenceRange,
    NarrationPlan,
    NarrationUnit,
    SemanticReviewDocument,
    SemanticUnitReview,
    Situation,
    SituationDocument,
    SituationTts,
    SituationTtsManifest,
    load_narration_plan,
    load_situations,
)


def _situation() -> Situation:
    return Situation(
        situation_id="situation-001",
        source_start_ms=10_000,
        source_end_ms=60_000,
        story_role="MAIN_PLOT",
        characters=("Jiro",),
        setup="Jiro bị băng nhóm chặn đường.",
        new_information=("Băng nhóm chủ động tấn công Jiro.",),
        turning_points=("Jiro phản công.",),
        outcome="Jiro hạ cả băng.",
        transcript_refs=("transcript-001",),
        frame_refs=("frame-001",),
        previous_situation_id=None,
        next_situation_id=None,
        confidence=1.0,
    )


def _range() -> EvidenceRange:
    return EvidenceRange(
        range_id="range-001",
        situation_id="situation-001",
        source_start_ms=10_000,
        source_end_ms=14_000,
        shot_ids=("shot-001",),
        event_ids=("event-001",),
        transcript_refs=("transcript-001",),
        frame_refs=("frame-001",),
        story_fact="Băng nhóm lao vào đánh Jiro.",
    )


def _plan() -> NarrationPlan:
    return NarrationPlan(
        owner="LOCAL_EDITOR",
        policy_version="situation-v1",
        units=(
            NarrationUnit(
                unit_id="unit-001",
                situation_id="situation-001",
                factual_claims=("Băng nhóm tấn công Jiro.",),
                narration_text="Đám này vừa thấy Jiro là nhào vô kiếm chuyện ngay.",
                bridge_from_previous="",
                bridge_to_next="Xử xong đám tép riu, Jiro lại gặp chuyện lớn hơn.",
                evidence_ranges=(_range(),),
                status="LOCKED",
            ),
        ),
    )


def test_policy_rejects_fixed_keep_skip_formula() -> None:
    with pytest.raises(MvpError, match="fixed keep/skip"):
        EditorialPolicy(fixed_keep_ms=6_000, fixed_skip_ms=4_000)


def test_policy_rejects_invalid_playback_range() -> None:
    with pytest.raises(MvpError, match="playback-rate"):
        EditorialPolicy(minimum_playback_rate=1.4, maximum_playback_rate=1.3)


def test_situation_requires_transcript_and_frame_evidence() -> None:
    base = _situation()
    with pytest.raises(MvpError, match="transcript and frame"):
        Situation(
            situation_id=base.situation_id,
            source_start_ms=base.source_start_ms,
            source_end_ms=base.source_end_ms,
            story_role=base.story_role,
            characters=base.characters,
            setup=base.setup,
            new_information=base.new_information,
            turning_points=base.turning_points,
            outcome=base.outcome,
            transcript_refs=(),
            frame_refs=base.frame_refs,
            previous_situation_id=None,
            next_situation_id=None,
            confidence=base.confidence,
        )


def test_narration_plan_requires_local_editor_owner() -> None:
    with pytest.raises(MvpError, match="LOCAL_EDITOR"):
        NarrationPlan("ANTIGRAVITY", "situation-v1", _plan().units)


def test_situation_tts_requires_sha256_cache_key() -> None:
    with pytest.raises(MvpError, match="cache key"):
        SituationTts("unit-001", "unit.mp3", "unit.wav", 2_000, "not-a-sha")


def test_semantic_review_owner_is_local_auditor() -> None:
    unit = SemanticUnitReview(
        unit_id="unit-001",
        supported=True,
        finding_codes=(),
        transcript_refs=("transcript-001",),
        source_frame_refs=("source-frame-001",),
        program_frame_refs=("program-frame-001",),
        note="Hình và lời cùng thể hiện vụ tấn công.",
    )
    with pytest.raises(MvpError, match="LOCAL_SEMANTIC_AUDITOR"):
        SemanticReviewDocument("GEMINI", (unit,))


def test_strict_json_round_trip(tmp_path: Path) -> None:
    situations = SituationDocument("LOCAL_EDITOR", "situation-v1", (_situation(),))
    plan = _plan()
    situation_path = tmp_path / "situations.json"
    plan_path = tmp_path / "narration_plan.json"
    dump_json(situation_path, situations)
    dump_json(plan_path, plan)

    assert load_situations(situation_path) == situations
    assert load_narration_plan(plan_path) == plan


def test_tts_manifest_total_matches_unit_durations() -> None:
    item = SituationTts("unit-001", "unit.mp3", "unit.wav", 2_000, "a" * 64)
    with pytest.raises(MvpError, match="total duration"):
        SituationTtsManifest(
            units=(item,),
            narration_wav_path="narration.wav",
            provider="fake",
            voice_id="voice-001",
            policy_version="situation-v1",
            cache_hits=0,
            cache_misses=1,
            total_duration_ms=1_999,
        )
