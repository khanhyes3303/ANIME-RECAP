from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import (
    Shot,
    ShotDocument,
    SourceRef,
    TranscriptDocument,
    TranscriptSegment,
)
from anime_review_mvp.situation_index import (
    SituationIndexDocument,
    SituationIndexEntry,
    load_situation_index,
    next_editable_situation,
    validate_situation_index,
)

SOURCE = SourceRef("episode.mp4", "a" * 64, 20_000, 1920, 1080, "1/1000", 1)
TRANSCRIPT = TranscriptDocument(
    "en",
    (
        TranscriptSegment(1_000, 2_000, "First", ()),
        TranscriptSegment(8_000, 9_000, "Second", ()),
    ),
)
SHOTS = ShotDocument(
    (
        Shot("shot-001", 0, 5_000),
        Shot("shot-002", 5_000, 10_000),
        Shot("shot-003", 10_000, 20_000),
    )
)
FRAMES = (
    "C:/frames/shot-001.jpg",
    "C:/frames/shot-002.jpg",
    "C:/frames/shot-003.jpg",
)


def entry(
    situation_id: str,
    start_ms: int,
    end_ms: int,
    *,
    segment_indexes: tuple[int, ...] = (),
    shot_ids: tuple[str, ...] = (),
    frame_refs: tuple[str, ...] = (),
    excluded: bool = False,
    exclusion_reason: str = "",
) -> SituationIndexEntry:
    return SituationIndexEntry(
        situation_id,
        start_ms,
        end_ms,
        "Tóm tắt có nghĩa",
        "Thiết lập hoặc đẩy cốt truyện",
        "Mục tiêu hoặc kết quả đã đổi",
        segment_indexes,
        shot_ids,
        frame_refs,
        excluded,
        exclusion_reason,
    )


def document(*entries: SituationIndexEntry) -> SituationIndexDocument:
    return SituationIndexDocument("ANTIGRAVITY", "situation-index-v1", "a" * 64, entries)


def test_valid_index_is_ordered_and_selects_next_unlocked_editable_entry() -> None:
    index = document(
        entry(
            "situation-001",
            0,
            5_000,
            shot_ids=("shot-001",),
            frame_refs=(FRAMES[0],),
            excluded=True,
            exclusion_reason="Opening",
        ),
        entry(
            "situation-002",
            5_000,
            10_000,
            segment_indexes=(1,),
            shot_ids=("shot-002",),
            frame_refs=(FRAMES[1],),
        ),
        entry("situation-003", 10_000, 20_000, shot_ids=("shot-003",)),
    )

    validate_situation_index(index, SOURCE, TRANSCRIPT, SHOTS, FRAMES)

    assert next_editable_situation(index, ()) == index.situations[1]
    assert next_editable_situation(index, ("situation-002",)) == index.situations[2]
    assert next_editable_situation(
        index, ("situation-002", "situation-003")
    ) is None


def test_editable_situation_rejects_publisher_bumper_frame(tmp_path: Path) -> None:
    frame = tmp_path / "shot-001.jpg"
    image = Image.new("RGB", (320, 180), "white")
    ImageDraw.Draw(image).rectangle((55, 35, 265, 145), fill=(230, 0, 0))
    image.save(frame)
    frame_ref = str(frame.resolve())
    index = document(
        entry(
            "situation-001",
            0,
            5_000,
            shot_ids=("shot-001",),
            frame_refs=(frame_ref,),
        ),
        entry(
            "situation-002",
            5_000,
            20_000,
            shot_ids=("shot-002", "shot-003"),
        ),
    )

    with pytest.raises(MvpError, match="SOURCE_FRAME_EXCLUDED_CONTENT: shot-001"):
        validate_situation_index(index, SOURCE, TRANSCRIPT, SHOTS, (frame_ref,))


def test_index_must_cover_source_without_gaps() -> None:
    shots = ShotDocument(
        (
            Shot("shot-001", 0, 5_000),
            Shot("shot-002", 5_000, 10_000),
        )
    )
    index = document(
        entry("situation-001", 0, 5_000, shot_ids=("shot-001",)),
        entry("situation-002", 5_000, 10_000, shot_ids=("shot-002",)),
    )

    with pytest.raises(MvpError, match="SITUATION_INDEX_SOURCE_GAP"):
        validate_situation_index(
            index,
            SourceRef("episode.mp4", "a" * 64, 15_000, 1920, 1080, "1/1000", 1),
            TRANSCRIPT,
            shots,
            FRAMES,
        )


def test_every_shot_belongs_to_exactly_one_situation() -> None:
    shots = ShotDocument(
        (
            Shot("shot-001", 0, 5_000),
            Shot("shot-002", 5_000, 10_000),
            Shot("shot-003", 10_000, 15_000),
        )
    )
    index = document(
        entry("situation-001", 0, 5_000, shot_ids=("shot-001",)),
        entry("situation-002", 5_000, 10_000, shot_ids=("shot-002",)),
    )

    with pytest.raises(MvpError, match="SITUATION_INDEX_SHOT_OWNERSHIP_INVALID"):
        validate_situation_index(
            index,
            SourceRef("episode.mp4", "a" * 64, 10_000, 1920, 1080, "1/1000", 1),
            TRANSCRIPT,
            shots,
            FRAMES,
        )


def test_situation_boundaries_must_snap_to_shot_edges() -> None:
    shots = ShotDocument(
        (
            Shot("shot-001", 0, 3_000),
            Shot("shot-002", 3_000, 5_000),
            Shot("shot-003", 5_000, 10_000),
        )
    )
    index = document(
        entry("situation-001", 0, 3_500, shot_ids=("shot-001", "shot-002")),
        entry("situation-002", 3_500, 10_000, shot_ids=("shot-002", "shot-003")),
    )

    with pytest.raises(MvpError, match="SITUATION_INDEX_BOUNDARY_NOT_ON_SHOT_EDGE"):
        validate_situation_index(
            index,
            SourceRef("episode.mp4", "a" * 64, 10_000, 1920, 1080, "1/1000", 1),
            TRANSCRIPT,
            shots,
            FRAMES,
        )


@pytest.mark.parametrize(
    ("bad_index", "message"),
    (
        (
            document(
                entry("situation-001", 0, 10_000, shot_ids=("shot-001", "shot-002")),
                entry("situation-002", 5_000, 20_000, shot_ids=("shot-002", "shot-003")),
            ),
            "overlap",
        ),
        (
            document(entry("situation-001", 0, 5_000, shot_ids=("missing",))),
            "shot",
        ),
        (
            document(entry("situation-001", 0, 5_000, segment_indexes=(5,))),
            "transcript",
        ),
        (
            document(
                entry(
                    "situation-001",
                    0,
                    5_000,
                    shot_ids=("shot-001",),
                    frame_refs=(FRAMES[2],),
                )
            ),
            "frame",
        ),
        (
            document(
                entry(
                    "situation-001",
                    0,
                    5_000,
                    shot_ids=("shot-001",),
                    excluded=True,
                    exclusion_reason="Opening",
                ),
                entry(
                    "situation-002",
                    5_000,
                    10_000,
                    shot_ids=("shot-002",),
                    excluded=True,
                    exclusion_reason="Recap",
                ),
                entry(
                    "situation-003",
                    10_000,
                    20_000,
                    shot_ids=("shot-003",),
                    excluded=True,
                    exclusion_reason="Ending",
                ),
            ),
            "editable",
        ),
    ),
)
def test_invalid_index_fails_closed(
    bad_index: SituationIndexDocument, message: str
) -> None:
    with pytest.raises(MvpError, match=message):
        validate_situation_index(bad_index, SOURCE, TRANSCRIPT, SHOTS, FRAMES)


def test_entry_rejects_invalid_id_and_missing_exclusion_reason() -> None:
    with pytest.raises(MvpError, match="situation ID"):
        entry("wrong-id", 0, 5_000, shot_ids=("shot-001",))
    with pytest.raises(MvpError, match="exclusion reason"):
        entry(
            "situation-001",
            0,
            5_000,
            shot_ids=("shot-001",),
            excluded=True,
        )


def test_load_rejects_wrong_source_hash(tmp_path: Path) -> None:
    path = tmp_path / "index.json"
    path.write_text(
        json.dumps(
            {
                "editor": "ANTIGRAVITY",
                "schema_version": "situation-index-v1",
                "source_sha256": "b" * 64,
                "situations": [
                    {
                        "situation_id": "situation-001",
                        "source_start_ms": 0,
                        "source_end_ms": 5000,
                        "summary": "Tóm tắt",
                        "story_purpose": "Thiết lập",
                        "boundary_reason": "Kết quả đổi",
                        "transcript_segment_indexes": [0],
                        "shot_ids": ["shot-001"],
                        "frame_refs": [FRAMES[0]],
                        "excluded": False,
                        "exclusion_reason": "",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MvpError, match="source hash"):
        load_situation_index(path, SOURCE, TRANSCRIPT, SHOTS, FRAMES)
