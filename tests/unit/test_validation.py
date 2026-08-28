from __future__ import annotations

from decimal import Decimal

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import (
    AuditFinding,
    AuditReport,
    Claim,
    EdlDocument,
    EdlSegment,
    Event,
    NarrationCue,
    SceneBeat,
    ScenePacket,
    SceneShot,
    ScriptDocument,
    SourceRegionAnnotation,
    TruthDocument,
    TtsCue,
    TtsManifest,
)
from anime_review_mvp.validation import (
    build_edl_from_scene_packets,
    coverage_ratio,
    cue_source_duration,
    validate_audit,
    validate_edl,
    validate_scene_packets,
    validate_script,
    validate_truth,
    validate_voice_lock,
)


def _truth(*, regions: tuple[SourceRegionAnnotation, ...] = ()) -> TruthDocument:
    return TruthDocument(
        events=(Event("event-001", 0, 10_000, ("A",), "A runs.", "MAIN", 1.0),),
        source_regions=regions,
        source_region_scan_complete=True,
    )


def _script(flags: list[bool]) -> ScriptDocument:
    return ScriptDocument(
        tuple(
            NarrationCue(
                f"cue-{index:03d}",
                "Noi dung",
                (f"claim-{index:03d}",),
                ("event-001",),
                supported,
            )
            for index, supported in enumerate(flags, start=1)
        )
    )


def _tts(durations: list[int]) -> TtsManifest:
    return TtsManifest(
        cues=tuple(
            TtsCue(f"cue-{index:03d}", "x.mp3", "x.wav", duration)
            for index, duration in enumerate(durations, start=1)
        ),
        narration_wav_path="narration.wav",
        provider="tiktok-capcut",
        voice_id="BV074_streaming",
    )


def _clean_audit() -> AuditReport:
    return AuditReport(True, "1", ())


def test_coverage_is_weighted_by_real_tts_duration() -> None:
    assert coverage_ratio(_script([True, True, False]), _tts([4_000, 4_000, 2_000])) == Decimal(
        "0.8"
    )


def test_coverage_below_threshold_fails() -> None:
    with pytest.raises(MvpError, match="0.80"):
        validate_audit(_clean_audit(), Decimal("0.799"))


def test_one_fact_contradiction_fails_even_with_full_coverage() -> None:
    audit = AuditReport(
        False,
        "1",
        (
            AuditFinding(
                "ERROR",
                "FACT_CONTRADICTION",
                "cue-001",
                "Wrong speaker",
                ("event-001",),
            ),
        ),
    )
    with pytest.raises(MvpError, match="FACT_CONTRADICTION"):
        validate_audit(audit, Decimal("1"))


def test_edl_requires_enough_one_to_one_footage_for_each_cue() -> None:
    edl = EdlDocument((EdlSegment("segment-001", "cue-001", 0, 3_000),))
    with pytest.raises(MvpError, match="footage duration"):
        validate_edl(edl, 10_000, _tts([4_000]), _truth())


def test_edl_rejects_excluded_opening_or_ending_region() -> None:
    opening = SourceRegionAnnotation(
        "region-001", 0, 9_000, "OPENING", "EXCLUDE", "Visible opening"
    )
    edl = EdlDocument((EdlSegment("segment-001", "cue-001", 1_000, 5_000),))
    with pytest.raises(MvpError, match="excluded source region"):
        validate_edl(edl, 1_200_000, _tts([4_000]), _truth(regions=(opening,)))


def test_script_rejects_event_ids_absent_from_truth() -> None:
    cue = NarrationCue("cue-001", "Sai canh", ("claim-001",), ("missing",), True)
    claim = Claim("claim-001", "ACTION", "Sai canh", ("missing",))
    with pytest.raises(MvpError, match="unknown event"):
        validate_script(ScriptDocument((cue,), (claim,)), _truth())


def test_script_rejects_claim_evidence_not_bound_to_its_cue() -> None:
    claim = Claim("claim-001", "ACTION", "A runs", ("event-001",))
    cue = NarrationCue("cue-001", "A chay", ("claim-001",), ("event-002",), True)
    truth = TruthDocument(
        events=(
            *_truth().events,
            Event("event-002", 10_000, 11_000, ("B",), "B waits.", "SIDE", 1.0),
        ),
        source_regions=(),
        source_region_scan_complete=True,
    )

    with pytest.raises(MvpError, match="claim evidence"):
        validate_script(ScriptDocument((cue,), (claim,)), truth)


def test_truth_rejects_overlapping_source_regions() -> None:
    regions = (
        SourceRegionAnnotation("r1", 0, 2_000, "OPENING", "EXCLUDE", "Opening"),
        SourceRegionAnnotation("r2", 1_000, 3_000, "OTHER", "KEEP_STORY", "Cold open"),
    )
    with pytest.raises(MvpError, match="overlap"):
        validate_truth(_truth(regions=regions), 10_000)


def _scene_packet(*, optional_end_ms: int = 5_000) -> ScenePacket:
    return ScenePacket(
        scene_id="scene-001",
        start_ms=0,
        end_ms=10_000,
        story_purpose="A bắt đầu giao chiến.",
        event_ids=("event-001",),
        shots=(
            SceneShot("shot-001", 0, 3_000, "MUST_KEEP", ("event-001",), "Hành động chính"),
            SceneShot("shot-002", 3_000, optional_end_ms, "OPTIONAL", ("event-001",), "Nhịp phụ"),
        ),
        beats=(
            SceneBeat(
                "beat-001",
                0,
                optional_end_ms,
                ("event-001",),
                ("shot-001", "shot-002"),
                ("cue-001",),
            ),
        ),
        cue_ids=("cue-001",),
    )


def _scene_script(*, duration_text: str = "A lao vào giao chiến.") -> ScriptDocument:
    return ScriptDocument(
        cues=(
            NarrationCue(
                "cue-001",
                duration_text,
                ("claim-001",),
                ("event-001",),
                True,
                "scene-001",
                ("beat-001",),
            ),
        ),
        claims=(Claim("claim-001", "ACTION", "A giao chiến", ("event-001",)),),
    )


def _scene_shots() -> tuple:
    from anime_review_mvp.models import Shot

    return (Shot("shot-001", 0, 3_000), Shot("shot-002", 3_000, 5_000))


def test_scene_packet_rejects_shot_outside_scene() -> None:
    packet = _scene_packet()
    broken = ScenePacket(
        packet.scene_id,
        packet.start_ms,
        packet.end_ms,
        packet.story_purpose,
        packet.event_ids,
        (
            SceneShot("shot-001", 0, 11_000, "MUST_KEEP", ("event-001",), "Too long"),
        ),
        packet.beats,
        packet.cue_ids,
    )
    with pytest.raises(MvpError, match="scene bounds"):
        validate_scene_packets((broken,), _truth(), _scene_shots(), 10_000)


def test_scene_packet_preserves_must_keep_and_many_shots() -> None:
    validate_scene_packets((_scene_packet(),), _truth(), _scene_shots(), 10_000)


def test_voice_lock_rejects_edl_that_omits_must_keep_shot() -> None:
    packet = _scene_packet()
    tts = _tts([3_000])
    edl = EdlDocument(
        (
            EdlSegment(
                "segment-001",
                "cue-001",
                3_000,
                5_000,
                "scene-001",
                "shot-002",
                "beat-001",
                ("event-001",),
                "OPTIONAL",
                0,
                2_000,
            ),
        )
    )
    with pytest.raises(MvpError, match="MUST_KEEP"):
        validate_voice_lock((packet,), _scene_script(), tts, edl)


def test_voice_lock_accepts_cue_covering_multiple_shots() -> None:
    packet = _scene_packet()
    tts = _tts([5_000])
    edl = EdlDocument(
        (
            EdlSegment(
                "segment-001",
                "cue-001",
                0,
                3_000,
                "scene-001",
                "shot-001",
                "beat-001",
                ("event-001",),
                "MUST_KEEP",
                0,
                3_000,
            ),
            EdlSegment(
                "segment-002",
                "cue-001",
                3_000,
                5_000,
                "scene-001",
                "shot-002",
                "beat-001",
                ("event-001",),
                "OPTIONAL",
                3_000,
                5_000,
            ),
        )
    )
    validate_voice_lock((packet,), _scene_script(), tts, edl)


def test_voice_lock_rejects_duration_drift_over_tolerance() -> None:
    packet = _scene_packet()
    tts = _tts([4_500])
    edl = EdlDocument(
        (
            EdlSegment(
                "segment-001",
                "cue-001",
                0,
                3_000,
                "scene-001",
                "shot-001",
                "beat-001",
                ("event-001",),
                "MUST_KEEP",
                0,
                3_000,
            ),
            EdlSegment(
                "segment-002",
                "cue-001",
                3_000,
                5_000,
                "scene-001",
                "shot-002",
                "beat-001",
                ("event-001",),
                "OPTIONAL",
                3_000,
                5_000,
            ),
        )
    )
    with pytest.raises(MvpError, match="voice-lock"):
        validate_voice_lock((packet,), _scene_script(), tts, edl)


def test_build_edl_trims_optional_shot_but_keeps_main_shot() -> None:
    packet = _scene_packet(optional_end_ms=7_000)
    edl = build_edl_from_scene_packets((packet,), _scene_script(), _tts([4_000]))

    assert cue_source_duration(edl, "cue-001") == 4_000
    assert [(segment.shot_id, segment.role) for segment in edl.segments] == [
        ("shot-001", "MUST_KEEP"),
        ("shot-002", "OPTIONAL"),
    ]
    assert edl.segments[-1].source_end_ms == 4_000
    assert edl.segments[0].program_start_ms == 0
    assert edl.segments[-1].program_end_ms == 4_000


def test_build_edl_rejects_tts_shorter_than_must_keep() -> None:
    with pytest.raises(MvpError, match="MUST_KEEP"):
        build_edl_from_scene_packets((_scene_packet(),), _scene_script(), _tts([2_000]))


def test_build_edl_program_timing_is_global_across_cues() -> None:
    first = _scene_packet()
    second = ScenePacket(
        "scene-002",
        10_000,
        14_000,
        "Scene tiếp theo.",
        ("event-001",),
        (SceneShot("shot-003", 10_000, 14_000, "MUST_KEEP", ("event-001",), "Chính"),),
        (SceneBeat("beat-002", 10_000, 14_000, ("event-001",), ("shot-003",), ("cue-002",)),),
        ("cue-002",),
    )
    script = ScriptDocument(
        cues=(
            _scene_script().cues[0],
            NarrationCue(
                "cue-002",
                "Scene tiếp theo.",
                ("claim-002",),
                ("event-001",),
                True,
                "scene-002",
                ("beat-002",),
            ),
        ),
        claims=(
            Claim("claim-001", "ACTION", "A giao chiến", ("event-001",)),
            Claim("claim-002", "ACTION", "Scene tiếp theo", ("event-001",)),
        ),
    )
    tts = _tts([5_000, 4_000])

    edl = build_edl_from_scene_packets((first, second), script, tts)

    assert edl.segments[2].program_start_ms == 5_000
    validate_voice_lock((first, second), script, tts, edl)
