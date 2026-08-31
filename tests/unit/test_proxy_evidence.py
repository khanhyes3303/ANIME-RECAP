from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from anime_review_mvp.adaptive_edl import AdaptiveEdlDocument, AdaptiveEdlSegment
from anime_review_mvp.models import (
    Shot,
    ShotDocument,
    SourceRef,
    TranscriptDocument,
    TranscriptSegment,
)
from anime_review_mvp.proxy_evidence import extract_cue_proxy_evidence
from anime_review_mvp.semantic_timeline import CueTiming, SemanticTimeline
from anime_review_mvp.situation_index import SituationIndexDocument, SituationIndexEntry
from anime_review_mvp.situations import (
    EvidenceRange,
    NarrationClaim,
    NarrationCue,
    NarrationPlan,
    NarrationUnit,
    SemanticShotUse,
)


class FakeRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> SimpleNamespace:
        self.commands.append(command)
        output = Path(command[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"frame")
        return SimpleNamespace(stdout="", stderr="", returncode=0)


def _source() -> SourceRef:
    return SourceRef(
        path="source.mp4",
        sha256="a" * 64,
        duration_ms=2_500,
        width=1_920,
        height=1_080,
        time_base="1/1000",
        audio_stream_count=1,
    )


def _transcript() -> TranscriptDocument:
    return TranscriptDocument(
        "en",
        (
            TranscriptSegment(1_000, 1_400, "Jiro gặp Rago.", ()),
            TranscriptSegment(1_400, 1_900, "Rago cảnh báo Jiro.", ()),
        ),
    )


def _shots() -> ShotDocument:
    return ShotDocument(
        (
            Shot("shot-0001", 0, 1_000),
            Shot("shot-0002", 1_000, 2_000),
            Shot("shot-0003", 2_000, 2_500),
        )
    )


def _index() -> SituationIndexDocument:
    return SituationIndexDocument(
        "ANTIGRAVITY",
        "situation-index-v1",
        "a" * 64,
        (
            SituationIndexEntry(
                "situation-000",
                0,
                1_000,
                "Intro",
                "Excluded intro",
                "Opening boundary",
                (0,),
                ("shot-0001",),
                ("frames/shot-0001.jpg",),
                True,
                "Intro credits",
            ),
            SituationIndexEntry(
                "situation-001",
                1_000,
                2_000,
                "Cue",
                "Main cue",
                "Scene boundary",
                (1,),
                ("shot-0002",),
                ("frames/shot-0002.jpg",),
                False,
                "",
            ),
            SituationIndexEntry(
                "situation-002",
                2_000,
                2_500,
                "Ending",
                "Excluded ending",
                "Ending boundary",
                (1,),
                ("shot-0003",),
                ("frames/shot-0003.jpg",),
                True,
                "Ending credits",
            ),
        ),
    )


def _plan() -> NarrationPlan:
    evidence = EvidenceRange(
        "range-001",
        "situation-001",
        1_000,
        2_000,
        ("shot-0002",),
        ("event-001",),
        ("Jiro gặp Rago.",),
        ("frames/shot-0002.jpg",),
        "Jiro gặp Rago.",
        "event-001",
        "ACTION",
        "Jiro gặp Rago.",
        (SemanticShotUse("shot-0002", "event-001", "ACTION", "Jiro gặp Rago."),),
    )
    cue = NarrationCue(
        "cue-001",
        "situation-001",
        "Jiro gặp Rago.",
        ("claim-001",),
        1_100,
        "ACTION",
        ("Jiro gặp Rago.",),
        ("frames/shot-0002.jpg",),
        ("shot-0002",),
        (),
        (),
        (),
        (),
        300,
        300,
    )
    unit = NarrationUnit(
        "unit-001",
        "situation-001",
        ("Jiro gặp Rago.",),
        "Jiro tìm thấy Rago.",
        "",
        "",
        (evidence,),
        "LOCKED",
        (cue,),
    )
    return NarrationPlan(
        "LOCAL_EDITOR",
        "situation-v2",
        (unit,),
        (NarrationClaim("claim-001", "Jiro gặp Rago.", ("event-001",)),),
    )


def _timeline() -> SemanticTimeline:
    return SemanticTimeline((CueTiming("cue-001", 1_500, 1_900, 1_100),), 1_900)


def _edl() -> AdaptiveEdlDocument:
    return AdaptiveEdlDocument(
        (
            AdaptiveEdlSegment(
                "segment-001",
                "unit-001",
                "situation-001",
                "range-001",
                1_000,
                2_000,
                0,
                1_000,
                1.0,
                ("shot-0002",),
                ("event-001",),
            ),
        ),
        1_000,
    )


def test_proxy_evidence_has_start_anchor_middle_end_for_every_cue(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    proxy = tmp_path / "proxy.mp4"
    source.write_bytes(b"source")
    proxy.write_bytes(b"proxy")

    manifest = extract_cue_proxy_evidence(
        source,
        proxy,
        _plan(),
        _timeline(),
        _edl(),
        _index(),
        _transcript(),
        tmp_path,
        runner=FakeRunner(),
    )

    assert tuple(frame.position for frame in manifest.cues[0].program_frames) == (
        "START",
        "ANCHOR",
        "MIDDLE",
        "END",
    )
    assert manifest.boundaries[0].boundary == "START"
    assert manifest.boundaries[-1].boundary == "END"
    assert manifest.boundaries[0].adjacent_excluded_source_intervals_ms
    assert manifest.boundaries[-1].adjacent_excluded_source_intervals_ms


def test_proxy_evidence_uses_exact_cue_range_not_whole_situation(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    proxy = tmp_path / "proxy.mp4"
    source.write_bytes(b"source")
    proxy.write_bytes(b"proxy")
    plan = _plan()
    second_range = EvidenceRange(
        "range-002",
        "situation-001",
        1_500,
        2_000,
        ("shot-0002",),
        ("event-002",),
        ("Rago cảnh báo Jiro.",),
        ("frames/shot-0002-b.jpg",),
        "Rago cảnh báo Jiro.",
        "event-002",
        "REACTION",
        "Rago cảnh báo Jiro.",
        (SemanticShotUse("shot-0002", "event-002", "REACTION", "Rago cảnh báo Jiro."),),
    )
    first_range = replace(plan.units[0].evidence_ranges[0], source_end_ms=1_500)
    first_cue = replace(plan.units[0].cues[0], visual_anchor_source_ms=1_100)
    second_cue = replace(
        first_cue,
        cue_id="cue-002",
        text="Rago cảnh báo Jiro.",
        claim_ids=("claim-002",),
        visual_anchor_source_ms=1_700,
        transcript_refs=("Rago cảnh báo Jiro.",),
        frame_refs=("frames/shot-0002-b.jpg",),
    )
    unit = replace(
        plan.units[0],
        evidence_ranges=(first_range, second_range),
        cues=(first_cue, second_cue),
    )
    plan = NarrationPlan(
        "LOCAL_EDITOR",
        "situation-v2",
        (unit,),
        (
            plan.claims[0],
            NarrationClaim("claim-002", "Rago cảnh báo Jiro.", ("event-002",)),
        ),
    )
    timeline = SemanticTimeline(
        (
            CueTiming("cue-001", 100, 450, 100),
            CueTiming("cue-002", 550, 900, 700),
        ),
        1_000,
    )
    edl = AdaptiveEdlDocument(
        (
            replace(
                _edl().segments[0],
                source_end_ms=1_500,
                program_end_ms=500,
            ),
            AdaptiveEdlSegment(
                "segment-002",
                "unit-001",
                "situation-001",
                "range-002",
                1_500,
                2_000,
                500,
                1_000,
                1.0,
                ("shot-0002",),
                ("event-002",),
            ),
        ),
        1_000,
    )
    manifest = extract_cue_proxy_evidence(
        source,
        proxy,
        plan,
        timeline,
        edl,
        _index(),
        _transcript(),
        tmp_path / "evidence",
        runner=FakeRunner(),
    )

    assert manifest.cues[0].source_interval_ms == (1_000, 1_500)
    assert manifest.cues[1].source_interval_ms == (1_500, 2_000)
    assert manifest.cues[0].transcript_text == ("Jiro gặp Rago.",)
    assert manifest.cues[1].transcript_text == ("Rago cảnh báo Jiro.",)
