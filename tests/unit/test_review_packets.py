from pathlib import Path
from types import SimpleNamespace

from anime_review_mvp.proxy_evidence import (
    BoundaryProxyEvidence,
    CueProxyEvidence,
    ProxyEvidenceFrame,
    ProxyEvidenceManifest,
)
from anime_review_mvp.review_packets import (
    build_proxy_audit_packet,
    validate_proxy_audit,
)


def _frames(prefix: str = "") -> tuple[ProxyEvidenceFrame, ...]:
    return tuple(
        ProxyEvidenceFrame(position, index * 100, f"{prefix}{position.lower()}.jpg")
        for index, position in enumerate(("START", "ANCHOR", "MIDDLE", "END"), 1)
    )


def _evidence(*cue_ids: str) -> ProxyEvidenceManifest:
    cues = tuple(
        CueProxyEvidence(
            cue_id,
            "situation-001",
            (0, 1_000),
            (0, 1_000),
            _frames("source-"),
            _frames("program-"),
            (0,),
            ("evidence",),
            ("shot-001",),
        )
        for cue_id in cue_ids
    )
    boundary = BoundaryProxyEvidence("START", _frames(), (), ())
    end = BoundaryProxyEvidence("END", _frames(), (), ())
    return ProxyEvidenceManifest(cues, (boundary, end))


def _plan(*cue_ids: str) -> SimpleNamespace:
    cue_items = tuple(SimpleNamespace(cue_id=cue_id) for cue_id in cue_ids)
    return SimpleNamespace(units=(SimpleNamespace(cues=cue_items),))


def _review(
    cue_id: str,
    verdict: str = "MATCH",
    situation_id: str = "situation-001",
    *,
    observed_visual: str = "Jiro xuất hiện cạnh con mèo bị thương trong rừng.",
    narration_meaning: str = "Jiro phát hiện và cứu con mèo.",
) -> SimpleNamespace:
    return SimpleNamespace(
        cue_id=cue_id,
        situation_id=situation_id,
        verdict=verdict,
        finding_codes=(),
        frame_refs=tuple(
            f"{prefix}{position.lower()}.jpg"
            for prefix in ("source-", "program-")
            for position in ("START", "ANCHOR", "MIDDLE", "END")
        ),
        transcript_refs=("evidence",),
        voice_before_visual=False,
        mixed_semantics=False,
        observed_visual=observed_visual,
        narration_meaning=narration_meaning,
        note="Đã đối chiếu riêng cue này với tám frame bằng chứng.",
    )


def test_proxy_packet_has_independent_context_and_single_output() -> None:
    packet = build_proxy_audit_packet(
        _evidence("cue-001"),
        Path("loudness_report.json"),
        "producer:task:a" * 10,
        "verifier:task:b" * 10,
    )
    assert packet.required_outputs == ("proxy_audit_draft.json",)
    assert packet.producer_context_id != packet.verifier_context_id


def test_proxy_audit_requires_exactly_one_match_for_every_cue() -> None:
    audit = SimpleNamespace(
        cue_reviews=(_review("cue-001"),),
        boundary_reviews=(SimpleNamespace(boundary="START", verdict="CLEAN"),),
    )
    result = validate_proxy_audit(
        audit,
        _plan("cue-001", "cue-002"),
        _evidence("cue-001", "cue-002"),
    )
    assert "PROXY_AUDIT_CUE_COVERAGE_INVALID" in result.finding_codes


def test_proxy_audit_rejects_intro_at_start_boundary() -> None:
    audit = SimpleNamespace(
        cue_reviews=(_review("cue-001"),),
        boundary_reviews=(
            SimpleNamespace(boundary="START", verdict="LEAKED_EXCLUDED_CONTENT"),
            SimpleNamespace(boundary="END", verdict="CLEAN"),
        ),
    )
    result = validate_proxy_audit(audit, _plan("cue-001"), _evidence("cue-001"))
    assert "INTRO_OPENING_LEAK" in result.finding_codes


def test_proxy_audit_rejects_cue_scope_mismatch() -> None:
    audit = SimpleNamespace(
        cue_reviews=(_review("cue-001", situation_id="situation-999"),),
        boundary_reviews=(
            SimpleNamespace(boundary="START", verdict="CLEAN"),
            SimpleNamespace(boundary="END", verdict="CLEAN"),
        ),
    )
    result = validate_proxy_audit(audit, _plan("cue-001"), _evidence("cue-001"))
    assert "PROXY_EVIDENCE_SCOPE_INVALID" in result.finding_codes


def test_proxy_audit_rejects_match_without_all_eight_cue_frames() -> None:
    review = _review("cue-001")
    review.frame_refs = review.frame_refs[:-1]
    audit = SimpleNamespace(
        cue_reviews=(review,),
        boundary_reviews=(
            SimpleNamespace(boundary="START", verdict="CLEAN"),
            SimpleNamespace(boundary="END", verdict="CLEAN"),
        ),
    )

    result = validate_proxy_audit(audit, _plan("cue-001"), _evidence("cue-001"))

    assert "PROXY_CUE_FRAME_COVERAGE_INVALID" in result.finding_codes


def test_proxy_audit_rejects_insufficient_boundary_evidence() -> None:
    audit = SimpleNamespace(
        cue_reviews=(_review("cue-001"),),
        boundary_reviews=(
            SimpleNamespace(boundary="START", verdict="INSUFFICIENT_EVIDENCE"),
            SimpleNamespace(boundary="END", verdict="CLEAN"),
        ),
    )
    result = validate_proxy_audit(audit, _plan("cue-001"), _evidence("cue-001"))
    assert "PROXY_BOUNDARY_EVIDENCE_INVALID" in result.finding_codes


def test_proxy_audit_rejects_transcript_as_narration_meaning() -> None:
    review = _review("cue-001", narration_meaning="evidence")
    audit = SimpleNamespace(
        cue_reviews=(review,),
        boundary_reviews=(
            SimpleNamespace(boundary="START", verdict="CLEAN"),
            SimpleNamespace(boundary="END", verdict="CLEAN"),
        ),
    )

    result = validate_proxy_audit(audit, _plan("cue-001"), _evidence("cue-001"))

    assert "PROXY_AUDIT_NARRATION_MEANING_INVALID" in result.finding_codes


def test_proxy_audit_rejects_repeated_visual_template() -> None:
    audit = SimpleNamespace(
        cue_reviews=(
            _review(
                "cue-001",
                observed_visual="Hình ảnh video proxy đúng nội dung trong shot-001.",
            ),
            _review(
                "cue-002",
                observed_visual="Hình ảnh video proxy đúng nội dung trong shot-002.",
            ),
        ),
        boundary_reviews=(
            SimpleNamespace(boundary="START", verdict="CLEAN"),
            SimpleNamespace(boundary="END", verdict="CLEAN"),
        ),
    )

    result = validate_proxy_audit(
        audit,
        _plan("cue-001", "cue-002"),
        _evidence("cue-001", "cue-002"),
    )

    assert "PROXY_AUDIT_BOILERPLATE_INVALID" in result.finding_codes
