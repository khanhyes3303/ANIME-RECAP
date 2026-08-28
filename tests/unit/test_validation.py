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
    ScriptDocument,
    SourceRegionAnnotation,
    TruthDocument,
    TtsCue,
    TtsManifest,
)
from anime_review_mvp.validation import (
    coverage_ratio,
    validate_audit,
    validate_edl,
    validate_script,
    validate_truth,
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
