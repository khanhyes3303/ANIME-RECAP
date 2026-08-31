from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .editor_provenance import EditorTask
from .errors import MvpError
from .proxy_evidence import ProxyEvidenceManifest
from .review_contracts import SituationAuditDocument
from .situation_scope import SituationScope
from .situations import NarrationPlan


@dataclass(frozen=True, slots=True)
class SituationAuditCue:
    cue_id: str
    situation_id: str
    text: str
    transcript_refs: tuple[str, ...]
    frame_refs: tuple[str, ...]
    shot_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SituationAuditPacket:
    situation_id: str
    source_start_ms: int
    source_end_ms: int
    scope_path: str
    transcript_path: str
    shots_path: str
    frames_path: str
    producer_task_id: str
    verifier_task_id: str
    producer_context_id: str
    verifier_context_id: str
    cues: tuple[SituationAuditCue, ...]
    required_outputs: tuple[str, ...] = ("situation_audit_draft.json",)


@dataclass(frozen=True, slots=True)
class ProxyAuditPacket:
    producer_context_id: str
    verifier_context_id: str
    evidence: ProxyEvidenceManifest
    loudness_report_path: str
    required_outputs: tuple[str, ...] = ("proxy_audit_draft.json",)


@dataclass(frozen=True, slots=True)
class ProxyAuditValidation:
    finding_codes: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.finding_codes


def build_situation_audit_packet(
    scope: SituationScope,
    plan: NarrationPlan,
    producer_task: EditorTask,
    verifier_task: EditorTask,
) -> SituationAuditPacket:
    if producer_task.task_kind != "SITUATION" or verifier_task.task_kind != "SITUATION_AUDIT":
        raise MvpError("VERIFIER_TASK_KIND_INVALID")
    if producer_task.situation_id != scope.situation_id or verifier_task.situation_id != scope.situation_id:
        raise MvpError("VERIFIER_SITUATION_SCOPE_INVALID")
    cues: list[SituationAuditCue] = []
    for unit in plan.units:
        if unit.situation_id != scope.situation_id:
            continue
        for cue in unit.cues:
            cues.append(
                SituationAuditCue(
                    cue.cue_id,
                    cue.situation_id,
                    cue.text,
                    cue.transcript_refs,
                    cue.frame_refs,
                    cue.shot_ids,
                )
            )
    if not cues:
        raise MvpError("VERIFIER_AUDIT_INVALID")
    producer_context = f"producer:{producer_task.task_id}:{producer_task.input_sha256}"
    verifier_context = f"verifier:{verifier_task.task_id}:{verifier_task.input_sha256}"
    return SituationAuditPacket(
        scope.situation_id,
        scope.source_start_ms,
        scope.source_end_ms,
        scope.scope_path,
        scope.transcript_path,
        scope.shots_path,
        scope.frames_path,
        producer_task.task_id,
        verifier_task.task_id,
        producer_context,
        verifier_context,
        tuple(cues),
    )


def render_situation_audit_prompt(packet: SituationAuditPacket) -> str:
    return (
        "Bạn là verifier độc lập của Antigravity. Chỉ kiểm định "
        f"{packet.situation_id}, đọc toàn bộ transcript/shots/frames trong packet và từng cue.\n"
        "Không sửa artifact của producer. Ghi đúng một situation_audit_draft.json.\n"
        "Mỗi cue phải có verdict MATCH, MISMATCH hoặc INSUFFICIENT_EVIDENCE; "
        "nếu frame/transcript không chứng minh lời dẫn thì bắt buộc dùng MISMATCH hoặc INSUFFICIENT_EVIDENCE.\n"
        f"Producer context: {packet.producer_context_id}\n"
        f"Verifier context: {packet.verifier_context_id}\n"
        "Không kết thúc luồng; sau khi ghi file, báo đường dẫn để chạy accept-verifier.\n"
    )


def validate_situation_audit(
    audit: SituationAuditDocument, plan: NarrationPlan
) -> SituationAuditDocument:
    expected = tuple(
        cue.cue_id
        for unit in plan.units
        if unit.situation_id == audit.situation_id
        for cue in unit.cues
    )
    observed = tuple(item.cue_id for item in audit.cue_reviews)
    if observed != expected or len(set(observed)) != len(observed):
        raise MvpError("SITUATION_AUDIT_CUE_COVERAGE_INVALID")
    if any(item.situation_id != audit.situation_id for item in audit.cue_reviews):
        raise MvpError("VERIFIER_SITUATION_SCOPE_INVALID")
    if any(item.verdict != "MATCH" for item in audit.cue_reviews):
        raise MvpError("SITUATION_AUDIT_FAILED")
    return audit


def build_proxy_audit_packet(
    evidence: ProxyEvidenceManifest,
    loudness_report_path: Path,
    producer_context_id: str,
    verifier_context_id: str,
) -> ProxyAuditPacket:
    if not producer_context_id.strip() or not verifier_context_id.strip() or producer_context_id == verifier_context_id:
        raise MvpError("VERIFIER_CONTEXT_NOT_INDEPENDENT")
    if len(evidence.boundaries) != 2:
        raise MvpError("VERIFIER_BOUNDARY_COVERAGE_INVALID")
    return ProxyAuditPacket(producer_context_id, verifier_context_id, evidence, str(loudness_report_path), ("proxy_audit_draft.json",))


def render_proxy_audit_prompt(packet: ProxyAuditPacket) -> str:
    """Render the single episode-level proxy verifier instruction."""
    return (
        "Bạn là verifier độc lập của Antigravity cho toàn bộ proxy. "
        "Đọc proxy evidence manifest, từng cue, transcript/SRT, source/program frames "
        "và loudness report; không tự suy đoán khi thiếu bằng chứng.\n"
        "Ghi đúng một proxy_audit_draft.json, gồm đúng một verdict cho mỗi cue "
        "(MATCH, MISMATCH hoặc INSUFFICIENT_EVIDENCE) và đúng hai boundary START/END.\n"
        "Kiểm tra voice có đi trước hình, cue có trộn nhiều tình huống, và START/END "
        "có lọt intro/opening/ending/credits/preview hay không.\n"
        f"Producer context: {packet.producer_context_id}\n"
        f"Verifier context: {packet.verifier_context_id}\n"
        "Không sửa artifact producer; sau khi ghi file báo đường dẫn để chạy accept-verifier.\n"
    )


def validate_proxy_audit(
    audit: object,
    plan: NarrationPlan,
    evidence: ProxyEvidenceManifest,
) -> ProxyAuditValidation:
    expected = tuple(cue.cue_id for unit in plan.units for cue in unit.cues)
    reviews = tuple(getattr(audit, "cue_reviews", ()))
    observed = tuple(item.cue_id for item in reviews)
    codes: list[str] = []
    if observed != expected or len(set(observed)) != len(observed):
        codes.append("PROXY_AUDIT_CUE_COVERAGE_INVALID")
    if len(getattr(audit, "boundary_reviews", ())) != 2:
        codes.append("VERIFIER_BOUNDARY_COVERAGE_INVALID")
    if any(item.verdict != "MATCH" for item in reviews):
        codes.extend(item.finding_codes or ("PROXY_CUE_MISMATCH",) for item in reviews if item.verdict != "MATCH")
    if any(item.boundary == "START" and item.verdict == "LEAKED_EXCLUDED_CONTENT" for item in getattr(audit, "boundary_reviews", ())):
        codes.append("INTRO_OPENING_LEAK")
    known = {item.cue_id for item in evidence.cues}
    if set(observed) - known:
        codes.append("PROXY_EVIDENCE_REFERENCE_INVALID")
    return ProxyAuditValidation(tuple(dict.fromkeys(code for item in codes for code in (item if isinstance(item, tuple) else (item,)))))
