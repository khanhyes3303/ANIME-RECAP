from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .editor_provenance import EditorTask
from .errors import MvpError
from .review_contracts import CueSemanticVerdict, SituationAuditDocument
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
