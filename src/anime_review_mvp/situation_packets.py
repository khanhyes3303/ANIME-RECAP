from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

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


@dataclass(frozen=True, slots=True)
class EpisodeReviewPacket:
    task_id: str
    run_id: str
    task_kind: Literal["EPISODE_REVIEW"]
    situation_id: Literal["__episode__"]
    revision: int
    input_sha256: str
    situation_index_path: str
    transcript_paths: tuple[str, ...]
    shot_manifest_path: str
    frame_manifest_path: str
    style_profile_path: str
    policy_path: str
    output_dir: str
    previous_situations_path: str = ""
    previous_narration_path: str = ""
    measured_voice_ms: int | None = None
    repair_code: str = ""
    required_outputs: tuple[str, str] = (
        "situations_draft.json",
        "narration_draft.json",
    )


def build_episode_review_packet(
    *,
    task: EditorTask,
    situation_index_path: Path,
    transcript_paths: tuple[Path, ...],
    shot_manifest_path: Path,
    frame_manifest_path: Path,
    style_profile_path: Path,
    policy_path: Path,
    output_dir: Path,
    previous_situations_path: Path | None = None,
    previous_narration_path: Path | None = None,
    measured_voice_ms: int | None = None,
    repair_code: str = "",
) -> EpisodeReviewPacket:
    inputs = (
        situation_index_path,
        *transcript_paths,
        shot_manifest_path,
        frame_manifest_path,
        style_profile_path,
        policy_path,
    )
    if (
        task.task_kind != "EPISODE_REVIEW"
        or task.situation_id != "__episode__"
        or task.allowed_outputs != ("situations_draft.json", "narration_draft.json")
        or not transcript_paths
        or any(not path.is_file() for path in inputs)
    ):
        raise MvpError("EPISODE_REVIEW_PACKET_INVALID")
    return EpisodeReviewPacket(
        task.task_id,
        task.run_id,
        "EPISODE_REVIEW",
        "__episode__",
        task.revision,
        task.input_sha256,
        str(situation_index_path.resolve()),
        tuple(str(path.resolve()) for path in transcript_paths),
        str(shot_manifest_path.resolve()),
        str(frame_manifest_path.resolve()),
        str(style_profile_path.resolve()),
        str(policy_path.resolve()),
        str(output_dir.resolve()),
        str(previous_situations_path.resolve()) if previous_situations_path else "",
        str(previous_narration_path.resolve()) if previous_narration_path else "",
        measured_voice_ms,
        repair_code,
    )


def render_episode_review_prompt(packet: EpisodeReviewPacket) -> str:
    transcripts = "\n".join(f"- `{path}`" for path in packet.transcript_paths)
    repair = ""
    if packet.repair_code:
        repair = (
            f"\nBản trước bị từ chối với `{packet.repair_code}`; tổng voice đo được "
            f"{packet.measured_voice_ms} ms. Sửa toàn bộ kế hoạch theo đúng diễn biến, "
            "không kéo dài riêng cảnh cuối.\n"
        )
    run_dir = Path(packet.output_dir).parents[1]
    accept_command = (
        f'accept-antigravity --run "{run_dir.resolve()}" --task {packet.task_id} '
        f'--input "{Path(packet.output_dir).resolve()}"'
    )
    return f"""Antigravity là biên tập viên cho một nhiệm vụ duy nhất cho toàn bộ tập phim.

Task `{packet.task_id}`, revision {packet.revision}, input SHA-256
`{packet.input_sha256}`. Không chia thành task biên tập, TTS, timeline hay verifier theo
từng tình huống. Hãy đọc `situation_index.json` tại `{packet.situation_index_path}` và giữ
mọi tình huống được chọn theo đúng thứ tự thời gian nguồn.

Nguồn transcript/SRT:
{transcripts}
Shots: `{packet.shot_manifest_path}`
Frames: `{packet.frame_manifest_path}`
Style: `{packet.style_profile_path}`
Policy: `{packet.policy_path}`

Bắt buộc xem trực tiếp các frame được tham chiếu. Đối chiếu transcript, SRT, shots và frames
tại cùng vị trí để xác định cảnh, tình huống và hành động.
Loại opening, ending, credits, preview, bumper, logo nhà phát hành và các mục excluded.
Không dùng
công thức lấy/bỏ số giây cố định; chọn hoặc bỏ theo ý nghĩa thật của cảnh.

Viết lời review tự nhiên như người kể chuyện, đủ nguyên nhân–diễn biến–kết quả, không
bịa và không lệch sang tình huống trước/sau. Lập đủ nội dung toàn tập để voice hợp lý nằm
trong 7–12 phút; mỗi cue tối đa 55 từ và khóa vào đúng evidence/visual anchor của nó.

Chỉ ghi đúng hai tệp vào `{packet.output_dir}`:
- `situations_draft.json`: mọi tình huống editable, đúng một lần, đúng thứ tự.
- `narration_draft.json`: mọi unit/claim/cue/evidence range tương ứng cùng thứ tự.

Không tạo script để tự sinh JSON, không đọc mã validator để tối ưu điều kiện PASS, không
ghi run_state/TTS/timeline/proxy và không phát `GOAL_COMPLETE`. Sau khi tự kiểm tra hai
tệp, chỉ chạy lệnh chấp nhận sau:

`{accept_command}`
{repair}"""


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
            (
                allowed_staging_dir or frame_manifest_path.parent / "editor_staging" / task.task_id
            ).resolve()
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
Mỗi cue chỉ được khóa vào đúng một evidence range chứa anchor, toàn bộ frame/shot và
transcript refs của cue. Không dùng chung phạm vi toàn tình huống để chứng minh hai câu
kể về hai hành động khác nhau. Voice của cue phải nằm trọn trong range đó.
Hình phải xuất hiện trước câu kể theo preroll. Viết đủ nguyên nhân–diễn biến–kết quả để
người chưa biết anime vẫn hiểu. Văn phong dân dã, tự nhiên, được thô tục khi hợp ngữ cảnh;
không bịa sự kiện, động cơ hoặc người nói. Mỗi cue tối đa 55 từ; nếu dài hơn phải tách
theo đúng hành động/cảnh và khóa mỗi cue mới vào bằng chứng riêng. Viết như người đang
kể chuyện bằng miệng: câu gọn, chủ động, ít tính từ; tránh lặp các cụm máy móc như
"vô cùng", "hoàn toàn", "ngay lập tức" và "tột độ".

Toàn tập sau khi ghép bắt buộc nằm trong {policy.target_minimum_ms}–
{policy.target_maximum_ms} ms. Viết đủ thông tin cốt truyện để voice toàn tập đạt ngân
sách này; không kéo dài bằng cảnh thừa, im lặng hoặc lặp ý. Các cue phải nối liên tục.
Đặt `visual_preroll_ms` khoảng 100–300 ms và `visual_postroll_ms` khoảng 50–150 ms để
khoảng nghỉ thông thường nằm trong 180–450 ms; tuyệt đối không quá 600 ms. Nếu tổng TTS
chưa thể đạt 7 phút, engine sẽ trả tình
huống về cho Antigravity viết lại; engine không tự kéo, nén hay viết thay.

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
