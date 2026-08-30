from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.situations import (
    CharacterContext,
    CueTts,
    CueTtsManifest,
    EditorialPolicy,
    EvidenceRange,
    NarrationClaim,
    NarrationCue,
    NarrationPlan,
    NarrationUnit,
    SemanticReviewDocument,
    SemanticShotUse,
    SemanticUnitReview,
    Situation,
    SituationDocument,
    SituationTts,
    SituationTtsManifest,
    StoryContext,
    TermContext,
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


def test_situation_allows_visual_only_evidence_but_not_empty_evidence() -> None:
    base = _situation()
    visual_only = replace(base, transcript_refs=())
    assert visual_only.frame_refs == ("frame-001",)

    with pytest.raises(MvpError, match="frame evidence"):
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
            frame_refs=(),
            previous_situation_id=None,
            next_situation_id=None,
            confidence=base.confidence,
        )


def test_narration_cue_allows_visual_only_evidence() -> None:
    cue = NarrationCue(
        "cue-visual",
        "situation-001",
        "Bị dồn tới đường cùng, Jiro bất ngờ biến hình.",
        ("claim-visual",),
        1_200,
        "REVEAL",
        (),
        ("frame-001",),
        ("shot-001",),
        (),
        (),
        (),
        (),
    )
    assert cue.transcript_refs == ()


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


def test_v2_narration_rejects_negative_visual_anchor() -> None:
    with pytest.raises(MvpError, match="visual anchor"):
        NarrationCue(
            cue_id="cue-001",
            situation_id="situation-001",
            text="Ông nội Jiro đã đứng chờ sẵn.",
            claim_ids=("claim-001",),
            visual_anchor_source_ms=-1,
            anchor_kind="CHARACTER_INTRO",
            transcript_refs=("transcript-001",),
            frame_refs=("frame-001",),
            shot_ids=("shot-001",),
            introduces_characters=("Ông nội",),
            mentions_characters=("Jiro", "Ông nội"),
            introduces_terms=(),
            mentions_terms=(),
        )


def test_v2_plan_requires_semantically_homogeneous_ranges() -> None:
    mixed_range = replace(
        _range(),
        semantic_event_id="event-001",
        action_phase="ACTION",
        story_purpose="Jiro phản công.",
        shot_uses=(
            SemanticShotUse("shot-001", "event-001", "ACTION", "Jiro phản công."),
            SemanticShotUse("shot-002", "event-002", "OUTCOME", "Đối thủ gục."),
        ),
    )
    cue = NarrationCue(
        "cue-001", "situation-001", "Jiro phản công.", ("claim-001",),
        10_000, "ACTION", ("transcript-001",), ("frame-001",), ("shot-001",),
        (), ("Jiro",), (), (),
    )
    unit = NarrationUnit(
        "unit-001", "situation-001", ("Jiro phản công.",), "Jiro phản công.",
        "", "", (mixed_range,), "LOCKED", (cue,),
    )
    with pytest.raises(MvpError, match="SEMANTIC_RANGE_MIXED"):
        NarrationPlan(
            "LOCAL_EDITOR", "situation-v2", (unit,),
            (NarrationClaim("claim-001", "Jiro phản công.", ("event-001",)),),
        )


def test_v2_contracts_accept_one_meaning_per_range() -> None:
    shot_use = SemanticShotUse("shot-001", "event-001", "ACTION", "Jiro phản công.")
    cue_tts = CueTts("cue-001", "unit-001", "cue.wav", "cue.mp3", 1_000, "a" * 64)
    manifest = CueTtsManifest((cue_tts,), "fake", "voice-001", "situation-v2", 0, 1)
    context = StoryContext(
        (CharacterContext("Jiro", "nhân vật chính", "cue-001"),),
        (TermContext("Hắc Tinh", "năng lực siêu nhiên", "cue-001"),),
        ("Ai đứng sau vụ tấn công?",),
        "Jiro thoát nạn.",
    )
    assert shot_use.action_phase == "ACTION"
    assert manifest.cues[0].cue_id == "cue-001"
    assert context.characters[0].name == "Jiro"


def test_legacy_v1_plan_loads_when_new_defaulted_fields_are_absent(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    raw = {
        "owner": "LOCAL_EDITOR",
        "policy_version": "situation-v1",
        "units": [{
            "unit_id": "unit-001", "situation_id": "situation-001",
            "factual_claims": ["Jiro phản công."], "narration_text": "Jiro phản công.",
            "bridge_from_previous": "", "bridge_to_next": "", "status": "LOCKED",
            "evidence_ranges": [{
                "range_id": "range-001", "situation_id": "situation-001",
                "source_start_ms": 10000, "source_end_ms": 14000,
                "shot_ids": ["shot-001"], "event_ids": ["event-001"],
                "transcript_refs": ["transcript-001"], "frame_refs": ["frame-001"],
                "story_fact": "Jiro phản công."
            }]
        }]
    }
    path.write_text(json.dumps(raw), encoding="utf-8")
    loaded = load_narration_plan(path)
    assert loaded.policy_version == "situation-v1"
    assert loaded.claims == ()
    assert loaded.units[0].cues == ()
