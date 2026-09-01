from __future__ import annotations

import re
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


def validate_audit_context(
    audit: object,
    *,
    producer_context_id: str,
    verifier_context_id: str,
    producer_task_id: str | None = None,
) -> None:
    """Reject an audit produced for any task other than the active pair."""
    if (
        getattr(audit, "producer_context_id", None) != producer_context_id
        or getattr(audit, "verifier_context_id", None) != verifier_context_id
        or (
            producer_task_id is not None
            and getattr(audit, "producer_task_id", None) != producer_task_id
        )
    ):
        raise MvpError("VERIFIER_TASK_CONTEXT_MISMATCH")


def semantic_review_signature(text: str) -> str:
    normalized = re.sub(r"\bshot(?:[-_\s]*\d+)?\b", "shot", text.casefold())
    normalized = re.sub(r"\d+", "", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    return " ".join(normalized.split())


def _echoes_narration(review_text: str, cue_text: str) -> bool:
    review = semantic_review_signature(review_text)
    cue = semantic_review_signature(cue_text)
    return bool(cue and len(cue.split()) >= 4 and cue in review)


def build_situation_audit_packet(
    scope: SituationScope,
    plan: NarrationPlan,
    producer_task: EditorTask,
    verifier_task: EditorTask,
) -> SituationAuditPacket:
    if producer_task.task_kind != "SITUATION" or verifier_task.task_kind != "SITUATION_AUDIT":
        raise MvpError("VERIFIER_TASK_KIND_INVALID")
    if (
        producer_task.situation_id != scope.situation_id
        or verifier_task.situation_id != scope.situation_id
    ):
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
    producer_context = (
        f"producer:{producer_task.task_id}:{producer_task.input_sha256}:"
        f"{producer_task.policy_sha256}"
    )
    verifier_context = (
        f"verifier:{verifier_task.task_id}:{verifier_task.input_sha256}:"
        f"{verifier_task.policy_sha256}"
    )
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
        "nếu frame/transcript không chứng minh lời dẫn thì bắt buộc dùng MISMATCH "
        "hoặc INSUFFICIENT_EVIDENCE.\n"
        f"Producer context: {packet.producer_context_id}\n"
        f"Verifier context: {packet.verifier_context_id}\n"
        "Không kết thúc luồng; sau khi ghi file, báo đường dẫn để chạy accept-verifier.\n"
    )


def validate_situation_audit(
    audit: SituationAuditDocument, plan: NarrationPlan
) -> SituationAuditDocument:
    expected_cues = tuple(
        cue
        for unit in plan.units
        if unit.situation_id == audit.situation_id
        for cue in unit.cues
    )
    expected = tuple(cue.cue_id for cue in expected_cues)
    observed = tuple(item.cue_id for item in audit.cue_reviews)
    if observed != expected or len(set(observed)) != len(observed):
        raise MvpError("SITUATION_AUDIT_CUE_COVERAGE_INVALID")
    if any(item.situation_id != audit.situation_id for item in audit.cue_reviews):
        raise MvpError("VERIFIER_SITUATION_SCOPE_INVALID")
    if any(item.verdict != "MATCH" for item in audit.cue_reviews):
        raise MvpError("SITUATION_AUDIT_FAILED")
    cue_by_id = {cue.cue_id: cue for cue in expected_cues}
    visual_signatures: list[str] = []
    for item in audit.cue_reviews:
        cue = cue_by_id[item.cue_id]
        visual = semantic_review_signature(item.observed_visual)
        narration = semantic_review_signature(item.narration_meaning)
        transcript = semantic_review_signature(" ".join(cue.transcript_refs))
        if (
            set(item.frame_refs) != set(cue.frame_refs)
            or set(item.transcript_refs) != set(cue.transcript_refs)
            or not visual
            or visual
            in {
                semantic_review_signature(
                    "Hình ảnh video proxy thể hiện chính xác nội dung câu chuyện trong shot"
                ),
                semantic_review_signature("Hình ảnh video proxy đúng nội dung trong shot"),
            }
            or not narration
            or (transcript and narration == transcript)
        ):
            raise MvpError("SITUATION_AUDIT_EVIDENCE_INVALID")
        if _echoes_narration(item.observed_visual, cue.text) or _echoes_narration(
            item.note, cue.text
        ):
            raise MvpError("SITUATION_AUDIT_NARRATION_ECHO_INVALID")
        visual_signatures.append(visual)
    if len(visual_signatures) != len(set(visual_signatures)):
        raise MvpError("SITUATION_AUDIT_EVIDENCE_INVALID")
    return audit


def build_proxy_audit_packet(
    evidence: ProxyEvidenceManifest,
    loudness_report_path: Path,
    producer_context_id: str,
    verifier_context_id: str,
) -> ProxyAuditPacket:
    if (
        not producer_context_id.strip()
        or not verifier_context_id.strip()
        or producer_context_id == verifier_context_id
    ):
        raise MvpError("VERIFIER_CONTEXT_NOT_INDEPENDENT")
    if len(evidence.boundaries) != 2:
        raise MvpError("VERIFIER_BOUNDARY_COVERAGE_INVALID")
    return ProxyAuditPacket(
        producer_context_id,
        verifier_context_id,
        evidence,
        str(loudness_report_path),
        ("proxy_audit_draft.json",),
    )


def render_proxy_audit_prompt(packet: ProxyAuditPacket) -> str:
    """Render the single episode-level proxy verifier instruction."""
    return (
        "Bạn là verifier độc lập của Antigravity cho toàn bộ proxy. "
        "Đọc proxy evidence manifest, từng cue, transcript/SRT, source/program frames "
        "và loudness report; không tự suy đoán khi thiếu bằng chứng.\n"
        "Ghi đúng một proxy_audit_draft.json, gồm đúng một verdict cho mỗi cue "
        "(MATCH, MISMATCH hoặc INSUFFICIENT_EVIDENCE) và đúng hai boundary START/END.\n"
        "Với từng cue phải thật sự mở và đối chiếu đủ tám frame: bốn SOURCE và bốn "
        "PROGRAM tại START, ANCHOR, MIDDLE, END; frame_refs trong verdict phải liệt kê "
        "đúng toàn bộ tám đường dẫn của cue. transcript_refs phải khớp transcript/SRT "
        "trong evidence. Thiếu một frame thì dùng INSUFFICIENT_EVIDENCE, không MATCH.\n"
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
        codes.extend(
            item.finding_codes or ("PROXY_CUE_MISMATCH",)
            for item in reviews
            if item.verdict != "MATCH"
        )
    if any(
        item.boundary == "START" and item.verdict == "LEAKED_EXCLUDED_CONTENT"
        for item in getattr(audit, "boundary_reviews", ())
    ):
        codes.append("INTRO_OPENING_LEAK")
    if any(
        item.boundary == "END" and item.verdict == "LEAKED_EXCLUDED_CONTENT"
        for item in getattr(audit, "boundary_reviews", ())
    ):
        codes.append("ENDING_CREDITS_LEAK")
    non_clean_boundaries = tuple(
        item for item in getattr(audit, "boundary_reviews", ()) if item.verdict != "CLEAN"
    )
    if non_clean_boundaries:
        codes.extend(
            getattr(item, "finding_codes", ()) or ("PROXY_BOUNDARY_EVIDENCE_INVALID",)
            for item in non_clean_boundaries
        )
    evidence_by_cue = {item.cue_id: item for item in evidence.cues}
    cue_by_id = {cue.cue_id: cue for unit in plan.units for cue in unit.cues}
    if set(observed) - set(evidence_by_cue):
        codes.append("PROXY_EVIDENCE_REFERENCE_INVALID")
    if any(
        item.cue_id in evidence_by_cue
        and item.situation_id != evidence_by_cue[item.cue_id].situation_id
        for item in reviews
    ):
        codes.append("PROXY_EVIDENCE_SCOPE_INVALID")
    for item in reviews:
        cue_evidence = evidence_by_cue.get(item.cue_id)
        if cue_evidence is None:
            continue
        expected_frames = {
            frame.path for frame in (*cue_evidence.source_frames, *cue_evidence.program_frames)
        }
        if set(getattr(item, "frame_refs", ())) != expected_frames:
            codes.append("PROXY_CUE_FRAME_COVERAGE_INVALID")
        if set(getattr(item, "transcript_refs", ())) != set(cue_evidence.transcript_text):
            codes.append("PROXY_CUE_TRANSCRIPT_COVERAGE_INVALID")
        if item.verdict == "MATCH" and (
            getattr(item, "voice_before_visual", False) or getattr(item, "mixed_semantics", False)
        ):
            codes.append("PROXY_CUE_MATCH_CONTRADICTS_FLAGS")
        transcript_meaning = semantic_review_signature(" ".join(cue_evidence.transcript_text))
        narration_meaning = semantic_review_signature(
            getattr(item, "narration_meaning", "")
        )
        if item.verdict == "MATCH" and (
            not narration_meaning or narration_meaning == transcript_meaning
        ):
            codes.append("PROXY_AUDIT_NARRATION_MEANING_INVALID")
        cue = cue_by_id.get(item.cue_id)
        if cue is not None and item.verdict == "MATCH" and any(
            _echoes_narration(value, cue.text)
            for value in (
                getattr(item, "observed_visual", ""),
                getattr(item, "narration_meaning", ""),
                getattr(item, "note", ""),
            )
        ):
            codes.append("PROXY_AUDIT_NARRATION_ECHO_INVALID")
    boundary_evidence = {item.boundary: item for item in evidence.boundaries}
    for item in getattr(audit, "boundary_reviews", ()):
        expected_boundary = boundary_evidence.get(item.boundary)
        expected_frames = (
            set()
            if expected_boundary is None
            else {frame.path for frame in expected_boundary.program_frames}
        )
        if expected_boundary is None or set(getattr(item, "frame_refs", ())) != expected_frames:
            codes.append("PROXY_BOUNDARY_EVIDENCE_INVALID")
        boundary_note = semantic_review_signature(getattr(item, "note", ""))
        if item.verdict == "CLEAN" and (
            not boundary_note or "hoàn toàn sạch" in boundary_note
        ):
            codes.append("PROXY_BOUNDARY_DESCRIPTION_INVALID")
    visual_signatures = tuple(
        semantic_review_signature(getattr(item, "observed_visual", ""))
        for item in reviews
        if item.verdict == "MATCH"
    )
    generic_visuals = {
        semantic_review_signature(
            "Hình ảnh video proxy thể hiện chính xác nội dung câu chuyện trong shot"
        ),
        semantic_review_signature("Hình ảnh video proxy đúng nội dung trong shot"),
    }
    generic_notes = {
        semantic_review_signature("Hình ảnh proxy, âm thanh và lời bình đồng bộ tuyệt đối"),
    }
    if any(not signature or signature in generic_visuals for signature in visual_signatures):
        codes.append("PROXY_AUDIT_BOILERPLATE_INVALID")
    if len(visual_signatures) != len(set(visual_signatures)):
        codes.append("PROXY_AUDIT_BOILERPLATE_INVALID")
    if any(
        semantic_review_signature(getattr(item, "note", "")) in generic_notes
        for item in reviews
    ):
        codes.append("PROXY_AUDIT_BOILERPLATE_INVALID")
    return ProxyAuditValidation(
        tuple(
            dict.fromkeys(
                code for item in codes for code in (item if isinstance(item, tuple) else (item,))
            )
        )
    )
