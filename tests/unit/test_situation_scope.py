from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import (
    Shot,
    ShotDocument,
    TranscriptDocument,
    TranscriptSegment,
)
from anime_review_mvp.situation_index import SituationIndexDocument, SituationIndexEntry
from anime_review_mvp.situation_scope import (
    load_situation_scope,
    materialize_situation_scope,
    validate_episode_submission_scope,
    validate_submission_scope,
)
from anime_review_mvp.situations import (
    EvidenceRange,
    NarrationCue,
    NarrationPlan,
    NarrationUnit,
    SemanticShotUse,
    Situation,
    SituationDocument,
)

ENTRY = SituationIndexEntry(
    "situation-002",
    5_000,
    10_000,
    "Jiro gặp kẻ địch",
    "Xung đột bắt đầu",
    "Đối thủ xuất hiện",
    (1,),
    ("shot-002", "shot-003"),
    ("C:/frames/shot-002.jpg", "C:/frames/shot-003.jpg"),
    False,
    "",
)
TRANSCRIPT = TranscriptDocument(
    "en",
    (
        TranscriptSegment(1_000, 2_000, "before", ()),
        TranscriptSegment(6_000, 7_000, "inside", ()),
        TranscriptSegment(11_000, 12_000, "after", ()),
    ),
)
SHOTS = ShotDocument(
    (
        Shot("shot-001", 0, 5_000),
        Shot("shot-002", 4_500, 7_000),
        Shot("shot-003", 7_000, 10_500),
        Shot("shot-004", 10_500, 15_000),
    )
)
FRAMES = (
    "C:/frames/shot-001.jpg",
    "C:/frames/shot-002.jpg",
    "C:/frames/shot-003.jpg",
    "C:/frames/shot-004.jpg",
)


def test_materialize_scope_contains_only_one_situation_evidence(tmp_path: Path) -> None:
    scope = materialize_situation_scope(
        tmp_path,
        ENTRY,
        TRANSCRIPT,
        SHOTS,
        FRAMES,
        accepted_index_sha256="a" * 64,
    )

    scoped_transcript = json.loads(Path(scope.transcript_path).read_text(encoding="utf-8"))
    scoped_shots = json.loads(Path(scope.shots_path).read_text(encoding="utf-8"))
    scoped_frames = json.loads(Path(scope.frames_path).read_text(encoding="utf-8"))

    assert [item["text"] for item in scoped_transcript["segments"]] == ["inside"]
    assert scoped_shots["shots"] == [
        {"shot_id": "shot-002", "start_ms": 5_000, "end_ms": 7_000},
        {"shot_id": "shot-003", "start_ms": 7_000, "end_ms": 10_000},
    ]
    assert scoped_frames["frames"] == [FRAMES[1], FRAMES[2]]
    assert all("frame_manifest.json" not in path for path in scope.input_paths)
    assert load_situation_scope(Path(scope.scope_path)) == scope


def test_scope_rejects_empty_or_stale_inputs(tmp_path: Path) -> None:
    no_evidence = SituationIndexEntry(
        "situation-009",
        16_000,
        18_000,
        "Không có dữ liệu",
        "Kiểm thử",
        "Khoảng trống",
        (),
        ("shot-009",),
        (),
        False,
        "",
    )
    with pytest.raises(MvpError, match="scope has no"):
        materialize_situation_scope(
            tmp_path,
            no_evidence,
            TRANSCRIPT,
            SHOTS,
            FRAMES,
            accepted_index_sha256="a" * 64,
        )

    scope = materialize_situation_scope(
        tmp_path,
        ENTRY,
        TRANSCRIPT,
        SHOTS,
        FRAMES,
        accepted_index_sha256="a" * 64,
    )
    Path(scope.transcript_path).write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(MvpError, match="scope hash"):
        load_situation_scope(Path(scope.scope_path), verify_files=True)


def test_scope_allows_visual_only_situation_without_dialogue(tmp_path: Path) -> None:
    visual_only = SituationIndexEntry(
        "situation-009",
        13_000,
        15_000,
        "Nhân vật biến hình",
        "Tiết lộ năng lực",
        "Trạng thái nhân vật thay đổi",
        (),
        ("shot-004",),
        ("C:/frames/shot-004.jpg",),
        False,
        "",
    )
    visual_shots = ShotDocument((*SHOTS.shots, Shot("shot-004", 10_000, 15_000)))

    scope = materialize_situation_scope(
        tmp_path,
        visual_only,
        TRANSCRIPT,
        visual_shots,
        FRAMES,
        accepted_index_sha256="a" * 64,
    )

    scoped = json.loads(Path(scope.transcript_path).read_text(encoding="utf-8"))
    assert scoped["segments"] == []


def _submission(source_start_ms: int, anchor_ms: int) -> tuple[SituationDocument, NarrationPlan]:
    shot_use = SemanticShotUse("shot-002", "event-001", "ACTION", "Xung đột")
    evidence = EvidenceRange(
        "range-001",
        "situation-002",
        source_start_ms,
        7_000,
        ("shot-002",),
        ("event-001",),
        ("segment-001",),
        (FRAMES[1],),
        "Kẻ địch xuất hiện",
        "event-001",
        "ACTION",
        "Xung đột",
        (shot_use,),
    )
    cue = NarrationCue(
        "cue-001",
        "situation-002",
        "Ngay lúc này kẻ địch mò tới.",
        ("claim-001",),
        anchor_ms,
        "ACTION",
        ("segment-001",),
        (FRAMES[1],),
        ("shot-002",),
        (),
        (),
        (),
        (),
    )
    situation = Situation(
        "situation-002",
        5_000,
        10_000,
        "MAIN_PLOT",
        ("Jiro",),
        "Jiro đang đứng một mình",
        ("Kẻ địch xuất hiện",),
        ("Xung đột bắt đầu",),
        "Hai bên đối đầu",
        ("segment-001",),
        (FRAMES[1],),
        None,
        None,
        0.9,
        cause_or_goal="Jiro bị chặn đường",
        audience_summary="Jiro gặp kẻ địch",
    )
    unit = NarrationUnit(
        "unit-001",
        "situation-002",
        ("Kẻ địch xuất hiện",),
        cue.text,
        "",
        "",
        (evidence,),
        "DRAFT",
        (cue,),
    )
    return (
        SituationDocument("LOCAL_EDITOR", "situation-v1", (situation,)),
        NarrationPlan("LOCAL_EDITOR", "situation-v1", (unit,), ()),
    )


def test_submission_scope_rejects_range_and_anchor_outside_boundary() -> None:
    situation, narration = _submission(4_900, 6_000)
    with pytest.raises(MvpError, match="outside active situation"):
        validate_submission_scope(ENTRY, situation, narration)

    situation, narration = _submission(5_000, 10_001)
    with pytest.raises(MvpError, match="visual anchor"):
        validate_submission_scope(ENTRY, situation, narration)


def test_episode_submission_requires_every_editable_situation_in_source_order() -> None:
    first_situations, first_narration = _submission(5_000, 6_000)
    second_entry = replace(
        ENTRY,
        situation_id="situation-003",
        source_start_ms=10_000,
        source_end_ms=15_000,
        shot_ids=("shot-004",),
        frame_refs=(FRAMES[3],),
    )
    index = SituationIndexDocument(
        "ANTIGRAVITY", "situation-index-v1", "a" * 64, (ENTRY, second_entry)
    )

    with pytest.raises(MvpError, match="EPISODE_SITUATION_COVERAGE_INVALID"):
        validate_episode_submission_scope(index, first_situations, first_narration)


def test_episode_submission_rejects_excluded_situation() -> None:
    situations, narration = _submission(5_000, 6_000)
    excluded = replace(ENTRY, excluded=True, exclusion_reason="opening")
    index = SituationIndexDocument(
        "ANTIGRAVITY", "situation-index-v1", "a" * 64, (excluded,)
    )

    with pytest.raises(MvpError, match="EPISODE_SITUATION_COVERAGE_INVALID"):
        validate_episode_submission_scope(index, situations, narration)

