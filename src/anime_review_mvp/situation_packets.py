from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import MvpError
from .models import ShotDocument, SourceRef, TranscriptDocument
from .situations import EditorialPolicy


@dataclass(frozen=True, slots=True)
class SituationEditorPacket:
    source: SourceRef
    transcript: TranscriptDocument
    shots: ShotDocument
    frame_manifest_path: str
    policy: EditorialPolicy
    prior_context: str
    required_outputs: tuple[str, ...] = ("situations.json", "narration_plan.json")

    def __post_init__(self) -> None:
        if not self.frame_manifest_path.strip():
            raise MvpError("frame manifest path must not be empty")
        if self.required_outputs != ("situations.json", "narration_plan.json"):
            raise MvpError("situation editor outputs do not match the local contract")


def build_situation_editor_packet(
    source: SourceRef,
    transcript: TranscriptDocument,
    shots: ShotDocument,
    frame_manifest_path: Path,
    policy: EditorialPolicy,
    prior_context: str | None,
) -> SituationEditorPacket:
    if not frame_manifest_path.is_file():
        raise MvpError(f"frame manifest does not exist: {frame_manifest_path}")
    return SituationEditorPacket(
        source=source,
        transcript=transcript,
        shots=shots,
        frame_manifest_path=str(frame_manifest_path.resolve()),
        policy=policy,
        prior_context=(prior_context or "").strip(),
    )


def render_situation_editor_prompt(packet: SituationEditorPacket) -> str:
    policy = packet.policy
    prior = packet.prior_context or "Không có ngữ cảnh tập trước."
    return f"""Bạn là biên tập viên local cho một tập anime.

Đọc transcript, shot và frame manifest `{packet.frame_manifest_path}` để hiểu chuyện.
Phân loại tình huống thành MAIN_PLOT | SUPPORTING_PLOT và hành động thành
MAIN_ACTION | SUPPORTING_ACTION | DECORATIVE. Không giữ hành động chỉ vì đẹp; chỉ giữ
hình chứng minh thông tin, nguyên nhân, quyết định, bước ngoặt hoặc kết quả đáng kể.

Không dùng công thức số giây cố định. Sau mỗi khoảng lấy phải có khoảng nguồn bị bỏ
thật sự ít nhất {policy.minimum_omitted_gap_ms} ms. Clip giữ tối thiểu
{policy.minimum_clip_ms} ms, tốc độ hình chỉ trong {policy.minimum_playback_rate:.2f}x–
{policy.maximum_playback_rate:.2f}x, và không dùng hình trước {policy.forbidden_before_ms} ms.

Xử lý tuần tự: xử lý xong và khóa một tình huống, lời Việt, evidence và bridge rồi mới
chuyển tình huống kế tiếp. Văn phong dân dã, tự nhiên, được thô tục khi hợp ngữ cảnh;
không bịa sự kiện, động cơ hoặc người nói.

Ngữ cảnh trước tập: {prior}

Chỉ ghi `situations.json` và `narration_plan.json` trong artifact của run. Không sửa
mã nguồn, test, policy, run_state.json, video nguồn hoặc tự cài công cụ. Không tự khai
PASS kỹ thuật; validator local quyết định.
"""
