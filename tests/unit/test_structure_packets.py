from __future__ import annotations

from pathlib import Path

from anime_review_mvp.editor_provenance import load_editor_task
from anime_review_mvp.models import (
    Shot,
    ShotDocument,
    SourceRef,
    TranscriptDocument,
    TranscriptSegment,
)
from anime_review_mvp.structure_packets import (
    build_structure_editor_packet,
    create_structure_task,
    render_structure_editor_prompt,
)


def test_structure_task_allows_only_situation_index(tmp_path: Path) -> None:
    run = tmp_path / "run"
    transcript = tmp_path / "transcript.json"
    shots = tmp_path / "shots.json"
    frames = tmp_path / "frames.json"
    for path in (transcript, shots, frames):
        path.write_text("{}", encoding="utf-8")

    task = create_structure_task(run, "run-001", 1, (transcript, shots, frames))
    loaded = load_editor_task(run / "editor_tasks" / f"{task.task_id}.json")

    assert task.task_kind == "STRUCTURE"
    assert task.task_id == "episode-structure-revision-001"
    assert task.situation_id == "__episode_structure__"
    assert task.allowed_outputs == ("situation_index_draft.json",)
    assert loaded == task


def test_structure_prompt_separates_boundaries_without_writing_narration(
    tmp_path: Path,
) -> None:
    frames = tmp_path / "frames.json"
    frames.write_text('{"frames":["C:/frames/shot-001.jpg"]}', encoding="utf-8")
    source = SourceRef("episode.mp4", "a" * 64, 10_000, 1920, 1080, "1/1000", 1)
    transcript = TranscriptDocument(
        "en", (TranscriptSegment(1_000, 2_000, "Who are you?", ()),)
    )
    shots = ShotDocument((Shot("shot-001", 0, 10_000),))
    inputs = tuple(
        path
        for path in (
            tmp_path / "transcript.json",
            tmp_path / "shots.json",
            frames,
        )
    )
    inputs[0].write_text("{}", encoding="utf-8")
    inputs[1].write_text("{}", encoding="utf-8")
    task = create_structure_task(tmp_path / "run", "run-001", 1, inputs)

    packet = build_structure_editor_packet(
        source, transcript, shots, frames, task=task
    )
    prompt = render_structure_editor_prompt(packet)

    assert "situation_index_draft.json" in prompt
    assert "transcript_segment_indexes" in prompt
    assert "boundary_reason" in prompt
    assert "opening" in prompt.casefold()
    assert "không viết lời review" in prompt.casefold()
    assert "narration_draft.json" not in prompt
    assert "Gemini Web" not in prompt
