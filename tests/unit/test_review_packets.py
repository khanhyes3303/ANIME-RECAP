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


def _frames() -> tuple[ProxyEvidenceFrame, ...]:
    return tuple(
        ProxyEvidenceFrame(position, index * 100, f"{position.lower()}.jpg")
        for index, position in enumerate(("START", "ANCHOR", "MIDDLE", "END"), 1)
    )


def _evidence(*cue_ids: str) -> ProxyEvidenceManifest:
    cues = tuple(
        CueProxyEvidence(
            cue_id,
            "situation-001",
            (0, 1_000),
            (0, 1_000),
            _frames(),
            _frames(),
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
) -> SimpleNamespace:
    return SimpleNamespace(
        cue_id=cue_id,
        situation_id=situation_id,
        verdict=verdict,
        finding_codes=(),
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
    result = validate_proxy_audit(
        audit, _plan("cue-001"), _evidence("cue-001")
    )
    assert "INTRO_OPENING_LEAK" in result.finding_codes


def test_proxy_audit_rejects_cue_scope_mismatch() -> None:
    audit = SimpleNamespace(
        cue_reviews=(_review("cue-001", situation_id="situation-999"),),
        boundary_reviews=(
            SimpleNamespace(boundary="START", verdict="CLEAN"),
            SimpleNamespace(boundary="END", verdict="CLEAN"),
        ),
    )
    result = validate_proxy_audit(
        audit, _plan("cue-001"), _evidence("cue-001")
    )
    assert "PROXY_EVIDENCE_SCOPE_INVALID" in result.finding_codes
