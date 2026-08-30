from __future__ import annotations

from dataclasses import replace

import pytest

from anime_review_mvp.adaptive_edl import build_adaptive_edl, choose_playback_rate
from anime_review_mvp.errors import MvpError
from anime_review_mvp.situations import (
    EditorialPolicy,
    EvidenceRange,
    NarrationPlan,
    NarrationUnit,
    SituationTts,
    SituationTtsManifest,
)

POLICY = EditorialPolicy(
    minimum_clip_ms=500,
    minimum_omitted_gap_ms=500,
    target_minimum_ms=1_000,
    target_maximum_ms=60_000,
)


def _range(range_id: str, start_ms: int, end_ms: int) -> EvidenceRange:
    return EvidenceRange(
        range_id=range_id,
        situation_id="situation-001",
        source_start_ms=start_ms,
        source_end_ms=end_ms,
        shot_ids=(f"shot-{range_id}",),
        event_ids=("event-001",),
        transcript_refs=("transcript-001",),
        frame_refs=(f"frame-{range_id}",),
        story_fact="Jiro phản công.",
    )


def _plan() -> NarrationPlan:
    return NarrationPlan(
        owner="LOCAL_EDITOR",
        policy_version="situation-v1",
        units=(
            NarrationUnit(
                unit_id="unit-001",
                situation_id="situation-001",
                factual_claims=("Jiro phản công.",),
                narration_text="Jiro quay lại cho cả đám ăn hành.",
                bridge_from_previous="",
                bridge_to_next="",
                evidence_ranges=(
                    _range("001", 1_000, 2_000),
                    _range("002", 3_000, 5_000),
                ),
                status="LOCKED",
            ),
        ),
    )


def _tts(duration_ms: int = 2_400, unit_id: str = "unit-001") -> SituationTtsManifest:
    item = SituationTts(unit_id, "unit.mp3", "unit.wav", duration_ms, "a" * 64)
    return SituationTtsManifest(
        units=(item,),
        narration_wav_path="narration.wav",
        provider="fake",
        voice_id="voice-001",
        policy_version="situation-v1",
        cache_hits=0,
        cache_misses=1,
        total_duration_ms=duration_ms,
    )


def test_voice_shorter_than_footage_uses_bounded_speedup() -> None:
    assert choose_playback_rate(3_000, 2_400, POLICY) == pytest.approx(1.25)


def test_rate_outside_policy_requests_narration_repair() -> None:
    with pytest.raises(MvpError, match="rewrite narration or select evidence"):
        choose_playback_rate(10_000, 2_000, POLICY)


def test_adaptive_edl_preserves_source_gap_and_matches_voice() -> None:
    edl = build_adaptive_edl(
        _plan(), _tts(), source_duration_ms=60_000, policy=POLICY
    )

    assert [segment.playback_rate for segment in edl.segments] == pytest.approx([1.25, 1.25])
    assert edl.segments[0].program_end_ms == 800
    assert edl.segments[1].program_start_ms == 800
    assert edl.segments[-1].program_end_ms == 2_400
    assert edl.total_duration_ms == 2_400


def test_adaptive_edl_requires_exact_tts_unit_ids() -> None:
    with pytest.raises(MvpError, match="unit IDs"):
        build_adaptive_edl(
            _plan(), _tts(unit_id="unit-missing"), source_duration_ms=60_000, policy=POLICY
        )


def test_adaptive_edl_requires_locked_units() -> None:
    plan = _plan()
    draft = NarrationPlan(
        plan.owner,
        plan.policy_version,
        (replace(plan.units[0], status="DRAFT"),),
    )

    with pytest.raises(MvpError, match="LOCKED"):
        build_adaptive_edl(draft, _tts(), source_duration_ms=60_000, policy=POLICY)
