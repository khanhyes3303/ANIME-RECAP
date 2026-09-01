from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp.editor_provenance import EditorTask
from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import (
    Shot,
    ShotDocument,
    SourceRef,
    TranscriptDocument,
    TranscriptSegment,
)
from anime_review_mvp.situation_index import SituationIndexEntry
from anime_review_mvp.situation_packets import (
    build_episode_review_packet,
    build_scoped_situation_editor_packet,
    build_situation_editor_packet,
    render_episode_review_prompt,
    render_situation_editor_prompt,
)
from anime_review_mvp.situation_scope import materialize_situation_scope
from anime_review_mvp.situations import EditorialPolicy, StoryContext

SOURCE = SourceRef("episode.mp4", "a" * 64, 60_000, 1920, 1080, "1/1000", 1)
TRANSCRIPT = TranscriptDocument(
    "en",
    (TranscriptSegment(1_000, 3_000, "Leave him alone.", ()),),
)
SHOTS = ShotDocument((Shot("shot-001", 1_000, 3_000),))
POLICY = EditorialPolicy(target_minimum_ms=1_000, target_maximum_ms=60_000)
TASK = EditorTask(
    "task-001",
    "run-001",
    "situation-004",
    2,
    "ANTIGRAVITY_EDITORIAL",
    ("transcript.json", "frames.json"),
    "a" * 64,
    ("situation_draft.json", "narration_draft.json"),
)


def test_packet_requires_frame_manifest_path() -> None:
    with pytest.raises(MvpError, match="frame manifest"):
        build_situation_editor_packet(
            SOURCE,
            TRANSCRIPT,
            SHOTS,
            Path(""),
            POLICY,
            StoryContext((), (), (), ""),
            task=TASK,
        )


def test_prompt_defines_local_situation_editor_contract(tmp_path: Path) -> None:
    frame_manifest = tmp_path / "frames.json"
    frame_manifest.write_text("{}", encoding="utf-8")
    packet = build_situation_editor_packet(
        SOURCE,
        TRANSCRIPT,
        SHOTS,
        frame_manifest,
        POLICY,
        StoryContext((), (), (), "Tập trước Jiro vừa gặp Rago."),
        task=TASK,
    )

    prompt = render_situation_editor_prompt(packet)
    normalized = prompt.casefold()

    assert "MAIN_PLOT | SUPPORTING_PLOT" in prompt
    assert "MAIN_ACTION | SUPPORTING_ACTION | DECORATIVE" in prompt
    assert "không giữ hành động chỉ vì đẹp" in normalized
    assert "sau mỗi khoảng lấy phải có khoảng nguồn bị bỏ" in normalized
    assert "mọi shot giao với khoảng" in normalized
    assert "source_start_ms" in normalized and "source_end_ms" in normalized
    assert "supporting_plot" in normalized and "future_payoff" in normalized
    assert "situation_draft.json" in prompt
    assert "narration_draft.json" in prompt
    assert "xử lý xong và khóa một tình huống" in normalized
    assert "xem trực tiếp video mẫu" not in normalized
    assert str(packet.policy.target_minimum_ms) in normalized
    assert str(packet.policy.target_maximum_ms) in normalized
    assert "mỗi cue chỉ được khóa vào đúng một evidence range" in normalized
    assert "600 ms" in normalized
    assert "tối đa 55 từ" in normalized
    assert "Gemini Web" not in prompt


def test_packet_preserves_prior_context_without_inventing_it(tmp_path: Path) -> None:
    frame_manifest = tmp_path / "frames.json"
    frame_manifest.write_text("{}", encoding="utf-8")

    packet = build_situation_editor_packet(
        SOURCE,
        TRANSCRIPT,
        SHOTS,
        frame_manifest,
        POLICY,
        StoryContext((), (), (), ""),
        task=TASK,
    )

    assert packet.prior_context.last_outcome == ""
    assert packet.task_kind == "SITUATION"
    assert packet.required_outputs == ("situation_draft.json", "narration_draft.json")


def test_packet_contains_exact_task_and_one_situation(tmp_path: Path) -> None:
    frame_manifest = tmp_path / "frames.json"
    frame_manifest.write_text("{}", encoding="utf-8")
    packet = build_situation_editor_packet(
        SOURCE,
        TRANSCRIPT,
        SHOTS,
        frame_manifest,
        POLICY,
        StoryContext((), (), (), ""),
        task=TASK,
    )
    assert (packet.task_id, packet.situation_id, packet.revision) == (
        "task-001",
        "situation-004",
        2,
    )


def test_prompt_forbids_codex_editor_and_direct_engine_writes(tmp_path: Path) -> None:
    frame_manifest = tmp_path / "frames.json"
    frame_manifest.write_text("{}", encoding="utf-8")
    packet = build_situation_editor_packet(
        SOURCE,
        TRANSCRIPT,
        SHOTS,
        frame_manifest,
        POLICY,
        StoryContext((), (), (), ""),
        task=TASK,
    )
    prompt = render_situation_editor_prompt(packet)
    assert "Antigravity là biên tập viên duy nhất" in prompt
    assert "không ghi run_state.json" in prompt
    assert "không ghi trực tiếp TTS" in prompt
    assert "visual_anchor_source_ms" in prompt
    assert "người chưa biết anime" in prompt
    assert "không đọc `revisions`" in prompt.casefold()
    assert "event_ids" in prompt


def test_scoped_packet_never_references_full_episode_manifest(tmp_path: Path) -> None:
    entry = SituationIndexEntry(
        "situation-004",
        1_000,
        3_000,
        "Jiro can thiệp",
        "Mở xung đột",
        "Mục tiêu thay đổi",
        (0,),
        ("shot-001",),
        ("C:/frames/shot-001.jpg",),
        False,
        "",
    )
    scope = materialize_situation_scope(
        tmp_path / "run",
        entry,
        TRANSCRIPT,
        SHOTS,
        ("C:/frames/shot-001.jpg",),
        accepted_index_sha256="b" * 64,
    )
    scoped_task = EditorTask(
        "task-scoped",
        "run-001",
        "situation-004",
        2,
        "ANTIGRAVITY_EDITORIAL",
        scope.input_paths,
        "a" * 64,
        ("situation_draft.json", "narration_draft.json"),
    )

    packet = build_scoped_situation_editor_packet(
        SOURCE,
        scope,
        POLICY,
        StoryContext((), (), (), ""),
        task=scoped_task,
    )

    assert packet.accepted_index_sha256 == "b" * 64
    assert packet.scope_path.endswith("scope.json")
    assert packet.frame_manifest_path.endswith("frames.json")
    assert "frame_manifest.json" not in packet.frame_manifest_path
    assert [segment.text for segment in packet.transcript.segments] == ["Leave him alone."]


def test_episode_packet_and_prompt_define_one_complete_editorial_job(tmp_path: Path) -> None:
    names = (
        "situation_index.json",
        "transcript.json",
        "episode.srt",
        "shots.json",
        "frames.json",
        "style.json",
        "policy.json",
    )
    paths = tuple(tmp_path / name for name in names)
    for path in paths:
        path.write_text("{}", encoding="utf-8")
    task = EditorTask(
        "__episode__-revision-001",
        "run-001",
        "__episode__",
        1,
        "ANTIGRAVITY_EDITORIAL",
        tuple(str(path.resolve()) for path in paths),
        "a" * 64,
        ("situations_draft.json", "narration_draft.json"),
        "EPISODE_REVIEW",
    )

    packet = build_episode_review_packet(
        task=task,
        situation_index_path=paths[0],
        transcript_paths=(paths[1], paths[2]),
        shot_manifest_path=paths[3],
        frame_manifest_path=paths[4],
        style_profile_path=paths[5],
        policy_path=paths[6],
        output_dir=tmp_path / "run" / "editor_staging" / task.task_id,
        measured_voice_ms=250_000,
        repair_code="EPISODE_VOICE_BUDGET_TOO_SHORT",
    )
    prompt = render_episode_review_prompt(packet)
    normalized = prompt.casefold()

    assert packet.task_kind == "EPISODE_REVIEW"
    assert packet.situation_id == "__episode__"
    assert "một nhiệm vụ duy nhất cho toàn bộ tập phim" in normalized
    assert "xem trực tiếp các frame" in normalized
    assert "transcript, srt, shots và frames" in normalized
    assert "đúng thứ tự thời gian nguồn" in normalized
    assert "opening, ending, credits, preview, bumper" in normalized
    assert "7–12 phút" in prompt
    assert "situations_draft.json" in prompt
    assert "narration_draft.json" in prompt
    assert "không tạo script" in normalized
    assert "không đọc mã validator" in normalized
    assert "không phát `goal_complete`" in normalized
    assert "accept-antigravity" in normalized
    assert "250000 ms" in normalized
