from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import Shot, ShotDocument
from anime_review_mvp.semantic_timeline import (
    CueTiming,
    build_semantic_timeline,
    map_source_timestamp,
    select_cue_source_window,
    semantic_timing_findings,
)
from anime_review_mvp.situations import (
    CueTts,
    CueTtsManifest,
    EditorialPolicy,
    EvidenceRange,
    NarrationClaim,
    NarrationCue,
    NarrationPlan,
    NarrationUnit,
    SemanticShotUse,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "black_torch_voice_ahead_30s" / "case.json"


def _plan() -> NarrationPlan:
    uses = (
        SemanticShotUse("shot-001", "event-approach", "APPROACH", "Jiro áp sát."),
        SemanticShotUse("shot-002", "event-outcome", "OUTCOME", "Đối thủ gục."),
    )
    ranges = (
        EvidenceRange(
            "range-approach",
            "situation-001",
            1_000,
            3_000,
            ("shot-001",),
            ("event-approach",),
            ("transcript-001",),
            ("frame-001",),
            "Jiro áp sát.",
            "event-approach",
            "APPROACH",
            "Jiro áp sát.",
            (uses[0],),
        ),
        EvidenceRange(
            "range-outcome",
            "situation-001",
            3_500,
            5_500,
            ("shot-002",),
            ("event-outcome",),
            ("transcript-002",),
            ("frame-002",),
            "Đối thủ gục.",
            "event-outcome",
            "OUTCOME",
            "Đối thủ gục.",
            (uses[1],),
        ),
    )
    cues = (
        NarrationCue(
            "cue-approach",
            "situation-001",
            "Jiro áp sát.",
            ("claim-001",),
            1_300,
            "ACTION",
            ("transcript-001",),
            ("frame-001",),
            ("shot-001",),
            ("Jiro",),
            ("Jiro",),
            (),
            (),
            300,
            300,
        ),
        NarrationCue(
            "cue-outcome",
            "situation-001",
            "Đối thủ gục.",
            ("claim-002",),
            3_800,
            "OUTCOME",
            ("transcript-002",),
            ("frame-002",),
            ("shot-002",),
            (),
            (),
            (),
            (),
            300,
            300,
        ),
    )
    unit = NarrationUnit(
        "unit-001",
        "situation-001",
        ("Jiro áp sát.", "Đối thủ gục."),
        "Jiro áp sát rồi hạ đối thủ.",
        "",
        "",
        ranges,
        "LOCKED",
        cues,
    )
    claims = (
        NarrationClaim("claim-001", "Jiro áp sát.", ("event-approach",)),
        NarrationClaim("claim-002", "Đối thủ gục.", ("event-outcome",)),
    )
    return NarrationPlan("LOCAL_EDITOR", "situation-v2", (unit,), claims)


def _tts() -> CueTtsManifest:
    return CueTtsManifest(
        (
            CueTts("cue-approach", "unit-001", "one.wav", "one.mp3", 1_000, "a" * 64),
            CueTts("cue-outcome", "unit-001", "two.wav", "two.mp3", 1_000, "b" * 64),
        ),
        "fake",
        "voice",
        "situation-v2",
        0,
        2,
    )


def test_black_torch_old_timeline_reports_voice_before_grandfather() -> None:
    case = json.loads(FIXTURE.read_text(encoding="utf-8"))
    timing = CueTiming(
        "cue-004-intro-grandfather",
        case["old_voice_start_ms"],
        case["old_voice_start_ms"] + case["cue_duration_ms"],
        case["visual_anchor_program_ms"],
    )
    codes = {finding.code for finding in semantic_timing_findings((timing,))}
    assert codes == {case["expected_finding"]}


def test_semantic_timing_reports_long_silence_and_trailing_dead_air() -> None:
    cues = (
        CueTiming("cue-001", 500, 1_500, 200),
        CueTiming("cue-002", 5_000, 6_000, 4_700),
    )

    codes = {finding.code for finding in semantic_timing_findings(cues, total_duration_ms=9_000)}

    assert "NARRATION_GAP_TOO_LONG" in codes
    assert "TRAILING_NARRATION_SILENCE" in codes


def test_new_timeline_places_voice_after_visual_preroll() -> None:
    edl, timeline = build_semantic_timeline(
        _plan(),
        _tts(),
        source_duration_ms=6_000,
        policy=EditorialPolicy(target_minimum_ms=1_000, target_maximum_ms=60_000),
    )
    assert [segment.range_id for segment in edl.segments] == ["range-approach", "range-outcome"]
    assert [cue.cue_id for cue in timeline.cues] == ["cue-approach", "cue-outcome"]
    assert all(cue.spoken_start_ms >= cue.visual_anchor_program_ms + 300 for cue in timeline.cues)
    assert semantic_timing_findings(timeline.cues) == ()
    assert edl.total_duration_ms == timeline.total_duration_ms
    assert map_source_timestamp(edl, 3_800) == timeline.cues[1].visual_anchor_program_ms


def test_cue_window_uses_only_the_compact_approved_shot() -> None:
    plan = _plan()
    cue = replace(
        plan.units[0].cues[0],
        visual_anchor_source_ms=1_000,
        shot_ids=("shot-001", "shot-extra"),
    )
    evidence = replace(
        plan.units[0].evidence_ranges[0],
        source_start_ms=1_000,
        source_end_ms=7_000,
        shot_ids=("shot-001", "shot-extra"),
    )
    shots = ShotDocument(
        (
            Shot("shot-001", 1_000, 4_000),
            Shot("shot-extra", 4_000, 7_000),
        )
    )

    window = select_cue_source_window(
        evidence,
        cue,
        shots,
        voice_ms=1_800,
        policy=EditorialPolicy(target_minimum_ms=1_000, target_maximum_ms=60_000),
    )

    assert window.source_start_ms == 1_000
    assert window.source_end_ms == 4_000
    assert window.shot_ids == ("shot-001",)
    assert window.playback_rate == pytest.approx(1.25)


def test_each_cue_range_selects_its_own_playback_rate() -> None:
    tts = replace(
        _tts(),
        cues=(
            _tts().cues[0],
            replace(_tts().cues[1], duration_ms=1_250),
        ),
    )

    edl, _ = build_semantic_timeline(
        _plan(),
        tts,
        source_duration_ms=6_000,
        policy=EditorialPolicy(target_minimum_ms=1_000, target_maximum_ms=60_000),
    )

    assert edl.segments[0].playback_rate != edl.segments[1].playback_rate


def test_277_seconds_voice_cannot_approve_764_seconds_evidence() -> None:
    plan = _plan()
    cue = replace(
        plan.units[0].cues[0],
        visual_anchor_source_ms=0,
        shot_ids=("shot-long",),
        frame_refs=("frame-long",),
        transcript_refs=("transcript-long",),
    )
    evidence = replace(
        plan.units[0].evidence_ranges[0],
        source_start_ms=0,
        source_end_ms=764_000,
        shot_ids=("shot-long",),
        frame_refs=("frame-long",),
        transcript_refs=("transcript-long",),
        shot_uses=(replace(plan.units[0].evidence_ranges[0].shot_uses[0], shot_id="shot-long"),),
    )
    unit = replace(plan.units[0], evidence_ranges=(evidence,), cues=(cue,))
    long_plan = replace(plan, units=(unit,))
    tts = replace(
        _tts(),
        cues=(replace(_tts().cues[0], duration_ms=277_000),),
        cache_misses=1,
    )

    with pytest.raises(MvpError, match="CUE_TIMELINE_DOES_NOT_FIT"):
        build_semantic_timeline(
            long_plan,
            tts,
            source_duration_ms=800_000,
            policy=EditorialPolicy(target_minimum_ms=1_000, target_maximum_ms=900_000),
            shots=ShotDocument((Shot("shot-long", 0, 764_000),)),
        )


def test_semantic_timeline_rejects_surplus_instead_of_compacting_accepted_ranges() -> None:
    plan = _plan()
    ranges = (
        replace(plan.units[0].evidence_ranges[0], source_end_ms=5_000),
        replace(
            plan.units[0].evidence_ranges[1],
            source_start_ms=6_000,
            source_end_ms=10_000,
        ),
    )
    cues = (
        replace(plan.units[0].cues[0], visual_anchor_source_ms=2_000),
        replace(plan.units[0].cues[1], visual_anchor_source_ms=7_000),
    )
    plan = replace(plan, units=(replace(plan.units[0], evidence_ranges=ranges, cues=cues),))
    with pytest.raises(MvpError, match="SEMANTIC_TIMELINE_DOES_NOT_FIT"):
        build_semantic_timeline(
            plan,
            _tts(),
            source_duration_ms=12_000,
            policy=EditorialPolicy(target_minimum_ms=1_000, target_maximum_ms=60_000),
        )


def test_semantic_timing_rejects_gap_above_reference_continuity_limit() -> None:
    cues = (
        CueTiming("cue-001", 100, 1_000, 0),
        CueTiming("cue-002", 2_201, 3_000, 2_000),
    )

    codes = {finding.code for finding in semantic_timing_findings(cues, 3_000)}

    assert "NARRATION_GAP_TOO_LONG" in codes
