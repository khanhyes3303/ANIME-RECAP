from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .editor_provenance import EditorTask, create_editor_task
from .errors import MvpError
from .models import ShotDocument, SourceRef, TranscriptDocument
from .reference_profile import ReferenceStyleProfile


@dataclass(frozen=True, slots=True)
class StructureEditorPacket:
    task_id: str
    run_id: str
    revision: int
    input_sha256: str
    allowed_staging_dir: str
    source: SourceRef
    transcript: TranscriptDocument
    shots: ShotDocument
    frame_manifest_path: str
    required_outputs: tuple[str, ...] = ("situation_index_draft.json",)
    task_kind: str = "STRUCTURE"
    reference: ReferenceStyleProfile = field(
        default=ReferenceStyleProfile("", "", 0, 0, 0),
        metadata={"json_optional": True},
    )

    def __post_init__(self) -> None:
        if not self.task_id.strip() or self.revision < 1:
            raise MvpError("structure task identity is invalid")
        if not self.frame_manifest_path.strip() or not self.allowed_staging_dir.strip():
            raise MvpError("structure frame manifest and staging paths are required")
        if self.required_outputs != ("situation_index_draft.json",):
            raise MvpError("structure task output contract is invalid")
        if self.task_kind != "STRUCTURE":
            raise MvpError("structure packet task kind is invalid")


def create_structure_task(
    run_dir: Path,
    run_id: str,
    revision: int,
    input_paths: tuple[Path, ...],
) -> EditorTask:
    return create_editor_task(
        run_dir,
        run_id,
        "__episode_structure__",
        revision,
        input_paths,
        task_kind="STRUCTURE",
        task_id=f"episode-structure-revision-{revision:03d}",
        allowed_outputs=("situation_index_draft.json",),
        expected_stage="ANTIGRAVITY_STRUCTURE",
    )


def build_structure_editor_packet(
    source: SourceRef,
    transcript: TranscriptDocument,
    shots: ShotDocument,
    frame_manifest_path: Path,
    *,
    task: EditorTask,
    allowed_staging_dir: Path | None = None,
    reference: ReferenceStyleProfile | None = None,
) -> StructureEditorPacket:
    if task.task_kind != "STRUCTURE":
        raise MvpError("structure packet requires a STRUCTURE task")
    if not frame_manifest_path.is_file():
        raise MvpError(f"frame manifest does not exist: {frame_manifest_path}")
    staging = allowed_staging_dir or (frame_manifest_path.parent / "editor_staging" / task.task_id)
    return StructureEditorPacket(
        task.task_id,
        task.run_id,
        task.revision,
        task.input_sha256,
        str(staging.resolve()),
        source,
        transcript,
        shots,
        str(frame_manifest_path.resolve()),
        task.allowed_outputs,
        reference=reference or ReferenceStyleProfile("", "", 0, 0, 0),
    )


def render_structure_editor_prompt(packet: StructureEditorPacket) -> str:
    return f"""Antigravity là biên tập viên duy nhất được chia cấu trúc tập phim.

Task `{packet.task_id}` chỉ lập chỉ mục tình huống từ transcript, shots và frame
manifest `{packet.frame_manifest_path}`. Không viết lời review, không chọn EDL, không
tạo TTS và không sửa mã nguồn hay run_state.json.

Transcript có thể rỗng ở cảnh visual-only. Khi đó phải dùng frame/shot làm bằng chứng
và không được bịa lời thoại. Nếu có transcript liên quan thì phải tham chiếu đúng index.

Một tình huống kết thúc khi mục tiêu, địa điểm, nhóm nhân vật, quan hệ nhân quả,
hành động có ý nghĩa hoặc kết quả thay đổi. Cùng là cảnh đánh nhau vẫn phải tách nếu
các shot lần lượt mang ý nghĩa tiếp cận, ra đòn, phản ứng hoặc kết quả khác nhau.
Ưu tiên ranh giới ngắn nhưng đồng nhất hơn một đoạn dài lộn xộn.

Mỗi entry phải có `situation_id`, `source_start_ms`, `source_end_ms`, `summary`,
`story_purpose`, `boundary_reason`, `transcript_segment_indexes`, `shot_ids`,
`frame_refs`, `excluded` và `exclusion_reason`. Đánh dấu opening, ending, recap,
credit, preview và nội dung dư bằng `excluded=true`. Mọi tham chiếu phải có thật và
nằm trong range. Range đầu tiên phải bắt đầu ở 0, range cuối phải kết thúc đúng
theo thời lượng source đã đo, các range kề nhau phải chạm biên nhau, mọi ranh giới
phải trùng với ranh giới shot thực tế, và mỗi `shot_id` phải xuất hiện đúng một
lần trên toàn bộ tập tình huống.

Ghi đúng cấu trúc JSON sau (thay các giá trị mẫu bằng bằng chứng thật):
{{
  "editor": "ANTIGRAVITY",
  "schema_version": "situation-index-v1",
  "source_sha256": "{packet.source.sha256}",
  "situations": [
    {{
      "situation_id": "situation-001",
      "source_start_ms": 0,
      "source_end_ms": 1000,
      "summary": "Tóm tắt điều đang xảy ra",
      "story_purpose": "Ý nghĩa đối với cốt truyện",
      "boundary_reason": "Lý do kết thúc tình huống tại đây",
      "transcript_segment_indexes": [0],
      "shot_ids": ["shot-0001"],
      "frame_refs": ["đường dẫn frame có thật trong manifest"],
      "excluded": false,
      "exclusion_reason": ""
    }}
  ]
}}

Chỉ ghi `situation_index_draft.json` vào `{packet.allowed_staging_dir}`. Không ghi
thêm bất kỳ artifact nào khác. Engine local sẽ kiểm schema, range, hash và
bằng chứng; Antigravity không tự cấp PASS. Nếu thiếu công cụ, báo người dùng và dừng.
"""
