from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .editor_provenance import EditorTask
from .errors import MvpError
from .jsonio import load_json
from .models import ShotDocument, SourceRef, TranscriptDocument
from .situation_scope import SituationScope, load_situation_scope
from .situations import EditorialPolicy, StoryContext


@dataclass(frozen=True, slots=True)
class SituationEditorPacket:
    task_id: str
    run_id: str
    situation_id: str
    revision: int
    input_sha256: str
    allowed_staging_dir: str
    source: SourceRef
    transcript: TranscriptDocument
    shots: ShotDocument
    frame_manifest_path: str
    policy: EditorialPolicy
    prior_context: StoryContext
    required_outputs: tuple[str, ...] = (
        "situation_draft.json",
        "narration_draft.json",
    )
    accepted_index_sha256: str = field(default="", metadata={"json_optional": True})
    scope_path: str = field(default="", metadata={"json_optional": True})
    task_kind: str = "SITUATION"
    repair_note: str = field(default="", metadata={"json_optional": True})

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.situation_id.strip() or self.revision < 1:
            raise MvpError("editor task identity is invalid")
        if not self.frame_manifest_path.strip() or not self.allowed_staging_dir.strip():
            raise MvpError("frame manifest path must not be empty")
        if self.required_outputs != ("situation_draft.json", "narration_draft.json"):
            raise MvpError("situation editor outputs do not match the local contract")
        if bool(self.accepted_index_sha256) != bool(self.scope_path):
            raise MvpError("situation scope hash and path must be supplied together")
        if self.task_kind != "SITUATION":
            raise MvpError("situation packet task kind is invalid")


def build_situation_editor_packet(
    source: SourceRef,
    transcript: TranscriptDocument,
    shots: ShotDocument,
    frame_manifest_path: Path,
    policy: EditorialPolicy,
    prior_context: StoryContext,
    *,
    task: EditorTask,
    allowed_staging_dir: Path | None = None,
    repair_note: str = "",
) -> SituationEditorPacket:
    if not frame_manifest_path.is_file():
        raise MvpError(f"frame manifest does not exist: {frame_manifest_path}")
    return SituationEditorPacket(
        task_id=task.task_id,
        run_id=task.run_id,
        situation_id=task.situation_id,
        revision=task.revision,
        input_sha256=task.input_sha256,
        allowed_staging_dir=str(
            (allowed_staging_dir or frame_manifest_path.parent / "editor_staging" / task.task_id)
            .resolve()
        ),
        source=source,
        transcript=transcript,
        shots=shots,
        frame_manifest_path=str(frame_manifest_path.resolve()),
        policy=policy,
        prior_context=prior_context,
        required_outputs=task.allowed_outputs,
        repair_note=repair_note,
    )


def build_scoped_situation_editor_packet(
    source: SourceRef,
    scope: SituationScope,
    policy: EditorialPolicy,
    prior_context: StoryContext,
    *,
    task: EditorTask,
    allowed_staging_dir: Path | None = None,
    repair_note: str = "",
) -> SituationEditorPacket:
    verified_scope = load_situation_scope(Path(scope.scope_path), verify_files=True)
    if verified_scope != scope or task.situation_id != scope.situation_id:
        raise MvpError("editor task does not match the accepted situation scope")
    if tuple(task.input_paths) != scope.input_paths:
        raise MvpError("editor task inputs must be exactly the scoped evidence files")
    transcript = load_json(Path(scope.transcript_path), TranscriptDocument)
    shots = load_json(Path(scope.shots_path), ShotDocument)
    staging = allowed_staging_dir or (
        Path(scope.scope_path).parents[2] / "editor_staging" / task.task_id
    )
    return SituationEditorPacket(
        task.task_id,
        task.run_id,
        task.situation_id,
        task.revision,
        task.input_sha256,
        str(staging.resolve()),
        source,
        transcript,
        shots,
        scope.frames_path,
        policy,
        prior_context,
        task.allowed_outputs,
        scope.accepted_index_sha256,
        scope.scope_path,
        task_kind="SITUATION",
        repair_note=repair_note,
    )


def render_situation_editor_prompt(packet: SituationEditorPacket) -> str:
    policy = packet.policy
    prior = packet.prior_context.last_outcome or "Không có ngữ cảnh trước đó."
    run_dir = Path(packet.allowed_staging_dir).parents[1]
    repair = (
        f"\nLỗi validator cần sửa trong vòng này: {packet.repair_note}\n"
        if packet.repair_note
        else ""
    )
    return f"""Antigravity là biên tập viên duy nhất của nội dung tập phim.

Bạn chỉ xử lý task `{packet.task_id}`, revision {packet.revision}, tình huống
`{packet.situation_id}`. Không xử lý tình huống khác trong lượt này. Input SHA-256 đã khóa:
`{packet.input_sha256}`.

Đọc transcript, shot và frame manifest thu hẹp `{packet.frame_manifest_path}` để hiểu chuyện.
Phạm vi đã khóa nằm trong `{packet.scope_path or "gói task"}`. Không đọc hoặc tham chiếu
transcript, shots hay frame manifest toàn tập ngoài gói này.
Không đọc `revisions`, `legacy_active`, truth/scene cũ hoặc task trước để bổ sung dữ liệu.
Tự đặt `event_ids` ổn định trong đúng tình huống từ transcript/frame/shot hiện tại; đây
chỉ là định danh bằng chứng cục bộ, không phải ID cần tra trong artifact legacy.
Phân loại tình huống thành MAIN_PLOT | SUPPORTING_PLOT và hành động thành
MAIN_ACTION | SUPPORTING_ACTION | DECORATIVE. Không giữ hành động chỉ vì đẹp; chỉ giữ
hình chứng minh thông tin, nguyên nhân, quyết định, bước ngoặt hoặc kết quả đáng kể.
Nếu chọn SUPPORTING_PLOT thì `future_payoff` bắt buộc phải có nội dung cụ thể; nếu
không có payoff về sau, hãy chọn MAIN_PLOT hoặc loại tình huống đó.

Mỗi evidence range phải có `semantic_event_id`, `action_phase`, `story_purpose` và
`shot_uses`. Mỗi shot trong range phải cùng đúng ba nhãn này. Nếu các shot lần lượt là
tiếp cận, ra đòn và phản ứng thì phải tách range, dù tất cả đều thuộc cùng một trận đánh.
Ưu tiên 4 giây cùng một tình huống/hành động/ý nghĩa hơn 10 giây lộn xộn.

Ranh giới mỗi range phải bám theo dữ liệu shot. Với khoảng
`source_start_ms`–`source_end_ms`, `shot_ids` phải liệt kê **mọi shot giao với khoảng
đó**, theo đúng thứ tự nguồn; không được chỉ liệt kê shot chính. `frame_refs` và
`shot_uses` cũng phải có đủ mọi shot giao với khoảng. Nếu không muốn lấy một shot,
hãy dời điểm bắt đầu/kết thúc ra ngoài shot đó.

Không dùng công thức số giây cố định. Sau mỗi khoảng lấy phải có khoảng nguồn bị bỏ
thật sự ít nhất {policy.minimum_omitted_gap_ms} ms. Clip giữ tối thiểu
{policy.minimum_clip_ms} ms, tốc độ hình chỉ trong {policy.minimum_playback_rate:.2f}x–
{policy.maximum_playback_rate:.2f}x, và không dùng hình trước {policy.forbidden_before_ms} ms.

Mỗi câu kể phải có `visual_anchor_source_ms`, transcript refs, frame refs và shot IDs.
Hình phải xuất hiện trước câu kể theo preroll. Viết đủ nguyên nhân–diễn biến–kết quả để
người chưa biết anime vẫn hiểu. Văn phong dân dã, tự nhiên, được thô tục khi hợp ngữ cảnh;
không bịa sự kiện, động cơ hoặc người nói.

Xử lý xong và khóa một tình huống rồi engine mới được chuyển sang tình huống kế tiếp.

{repair}

Ngữ cảnh trước tập: {prior}

Chỉ ghi `situation_draft.json` và `narration_draft.json` vào đúng thư mục staging:
`{packet.allowed_staging_dir}`; không ghi run_state.json, không ghi trực tiếp TTS, timeline,
EDL, audit hay video. Không sửa mã nguồn, test, policy, video nguồn và không tự cài công cụ.
Nếu thiếu công cụ, báo chính xác cho người dùng rồi dừng. Validator local quyết định PASS.

Sau khi ghi đủ hai file, chạy lệnh engine
`accept-antigravity --run "{run_dir}" --task {packet.task_id} --input
"{packet.allowed_staging_dir}"` được ghi trong next_action.json; không tự sửa trạng thái
hay giả mạo kết quả kiểm định.
"""
