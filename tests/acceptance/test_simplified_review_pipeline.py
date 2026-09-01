from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from anime_review_mvp.models import Shot, ShotDocument
from anime_review_mvp.proxy_evidence import (
    BoundaryProxyEvidence,
    CueProxyEvidence,
    ProxyEvidenceFrame,
    ProxyEvidenceManifest,
)
from anime_review_mvp.review_packets import validate_proxy_audit
from anime_review_mvp.semantic_timeline import build_semantic_timeline
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


def _episode_plan() -> tuple[NarrationPlan, CueTtsManifest, ShotDocument]:
    units: list[NarrationUnit] = []
    claims: list[NarrationClaim] = []
    tts: list[CueTts] = []
    shots: list[Shot] = []
    for number, (start_ms, end_ms) in enumerate(((0, 210_000), (210_500, 420_500)), 1):
        situation_id = f"situation-{number:03d}"
        cue_id = f"cue-{number:03d}"
        claim_id = f"claim-{number:03d}"
        shot_id = f"shot-{number:03d}"
        event_id = f"event-{number:03d}"
        transcript = f"transcript-{number:03d}"
        frame = f"frame-{number:03d}"
        meaning = f"Hành động cốt truyện thứ {number} diễn ra."
        shot_use = SemanticShotUse(shot_id, event_id, "ACTION", meaning)
        evidence = EvidenceRange(
            f"range-{number:03d}", situation_id, start_ms, end_ms, (shot_id,),
            (event_id,), (transcript,), (frame,), meaning, event_id, "ACTION",
            meaning, (shot_use,),
        )
        cue = NarrationCue(
            cue_id, situation_id, f"Lời review cho hành động thứ {number}.",
            (claim_id,), start_ms, "ACTION", (transcript,), (frame,), (shot_id,),
            ("Jiro",), ("Jiro",), (), (), 300, 300,
        )
        units.append(
            NarrationUnit(
                f"unit-{number:03d}", situation_id, (meaning,), cue.text, "", "",
                (evidence,), "LOCKED", (cue,),
            )
        )
        claims.append(NarrationClaim(claim_id, meaning, (event_id,)))
        tts.append(
            CueTts(
                cue_id, f"unit-{number:03d}", f"{cue_id}.wav", f"{cue_id}.mp3",
                209_400, f"{number}" * 64,
            )
        )
        shots.append(Shot(shot_id, start_ms, end_ms))
    return (
        NarrationPlan("LOCAL_EDITOR", "situation-v2", tuple(units), tuple(claims)),
        CueTtsManifest(tuple(tts), "fake", "voice", "situation-v2", 0, 2),
        ShotDocument(tuple(shots)),
    )


def _frames(prefix: str) -> tuple[ProxyEvidenceFrame, ...]:
    return tuple(
        ProxyEvidenceFrame(position, index * 100, f"{prefix}-{position.lower()}.jpg")
        for index, position in enumerate(("START", "ANCHOR", "MIDDLE", "END"), 1)
    )


def test_simplified_pipeline_builds_real_timeline_and_validates_evidence_offline() -> None:
    plan, tts, shots = _episode_plan()
    policy = EditorialPolicy()
    partial_plan = replace(plan, units=plan.units[:1], claims=plan.claims[:1])
    partial_tts = replace(tts, cues=tts.cues[:1], cache_misses=1)

    partial_edl, _ = build_semantic_timeline(
        partial_plan, partial_tts, 422_000, policy, shots,
        enforce_episode_duration=False,
    )
    edl, timeline = build_semantic_timeline(plan, tts, 422_000, policy, shots)

    assert partial_edl.total_duration_ms == 210_000
    assert edl.total_duration_ms == 420_000
    assert all(segment.playback_rate == 1.0 for segment in edl.segments)
    assert timeline.cues[1].spoken_start_ms - timeline.cues[0].spoken_end_ms <= 600

    cue_evidence = tuple(
        CueProxyEvidence(
            cue.cue_id, cue.situation_id,
            (segment.source_start_ms, segment.source_end_ms),
            (segment.program_start_ms, segment.program_end_ms),
            _frames(f"source-{cue.cue_id}"), _frames(f"program-{cue.cue_id}"),
            (index,), (f"transcript-{index + 1:03d}",), segment.shot_ids,
        )
        for index, (cue, segment) in enumerate(
            zip((unit.cues[0] for unit in plan.units), edl.segments, strict=True)
        )
    )
    evidence = ProxyEvidenceManifest(
        cue_evidence,
        (
            BoundaryProxyEvidence("START", _frames("boundary-start"), (), ()),
            BoundaryProxyEvidence("END", _frames("boundary-end"), (), ()),
        ),
    )
    observations = (
        ("Jiro mở cổng rồi lao vào sân.", "Lời review giải thích Jiro bắt đầu truy đuổi."),
        ("Rago chắn trước con quái vật trong rừng.", "Lời review giải thích Rago bảo vệ Jiro."),
    )
    reviews = tuple(
        SimpleNamespace(
            cue_id=item.cue_id, situation_id=item.situation_id, verdict="MATCH",
            finding_codes=(),
            frame_refs=tuple(frame.path for frame in (*item.source_frames, *item.program_frames)),
            transcript_refs=item.transcript_text, voice_before_visual=False,
            mixed_semantics=False,
            observed_visual=observations[index][0],
            narration_meaning=observations[index][1],
            note=f"Đã đối chiếu tám frame riêng cho {item.cue_id}.",
        )
        for index, item in enumerate(evidence.cues)
    )
    boundary_reviews = tuple(
            SimpleNamespace(
                boundary=item.boundary, verdict="CLEAN",
                frame_refs=tuple(frame.path for frame in item.program_frames),
                transcript_refs=(), finding_codes=(),
                note=(
                    "Khung đầu cho thấy Jiro bước vào sân, không có logo hay opening."
                    if item.boundary == "START"
                    else "Khung cuối cho thấy Rago đứng trong rừng, không có credit hay preview."
                ),
            )
        for item in evidence.boundaries
    )

    assert validate_proxy_audit(
        SimpleNamespace(cue_reviews=reviews, boundary_reviews=boundary_reviews),
        plan,
        evidence,
    ).passed is True
