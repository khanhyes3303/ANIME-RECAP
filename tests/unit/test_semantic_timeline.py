from __future__ import annotations

import json
from pathlib import Path

from anime_review_mvp.semantic_timeline import (
    CueTiming,
    build_semantic_timeline,
    map_source_timestamp,
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
            5_000,
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
            6_000,
            10_000,
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
            2_000,
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
            7_000,
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
        source_duration_ms=12_000,
        policy=EditorialPolicy(target_minimum_ms=1_000, target_maximum_ms=60_000),
    )
    assert [segment.range_id for segment in edl.segments] == ["range-approach", "range-outcome"]
    assert [cue.cue_id for cue in timeline.cues] == ["cue-approach", "cue-outcome"]
    assert all(cue.spoken_start_ms >= cue.visual_anchor_program_ms + 300 for cue in timeline.cues)
    assert semantic_timing_findings(timeline.cues) == ()
    assert edl.total_duration_ms == timeline.total_duration_ms
    assert map_source_timestamp(edl, 7_000) == timeline.cues[1].visual_anchor_program_ms


def test_semantic_timeline_cuts_surplus_video_between_narrated_cues() -> None:
    edl, timeline = build_semantic_timeline(
        _plan(),
        _tts(),
        source_duration_ms=12_000,
        policy=EditorialPolicy(target_minimum_ms=1_000, target_maximum_ms=60_000),
    )

    gaps = [
        following.spoken_start_ms - current.spoken_end_ms
        for current, following in zip(timeline.cues, timeline.cues[1:], strict=False)
    ]
    assert max(gaps) <= 2_500
    assert timeline.cues[0].spoken_start_ms <= 1_200
    assert timeline.total_duration_ms - timeline.cues[-1].spoken_end_ms <= 1_200
    assert timeline.total_duration_ms < 8_000
    assert edl.total_duration_ms == timeline.total_duration_ms
