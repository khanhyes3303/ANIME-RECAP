from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import (
    Shot,
    ShotDocument,
    SourceRef,
    TranscriptDocument,
    TranscriptSegment,
)
from anime_review_mvp.situation_packets import (
    build_situation_editor_packet,
    render_situation_editor_prompt,
)
from anime_review_mvp.situations import EditorialPolicy

SOURCE = SourceRef("episode.mp4", "a" * 64, 60_000, 1920, 1080, "1/1000", 1)
TRANSCRIPT = TranscriptDocument(
    "en",
    (TranscriptSegment(1_000, 3_000, "Leave him alone.", ()),),
)
SHOTS = ShotDocument((Shot("shot-001", 1_000, 3_000),))
POLICY = EditorialPolicy(target_minimum_ms=1_000, target_maximum_ms=60_000)


def test_packet_requires_frame_manifest_path() -> None:
    with pytest.raises(MvpError, match="frame manifest"):
        build_situation_editor_packet(SOURCE, TRANSCRIPT, SHOTS, Path(""), POLICY, None)


def test_prompt_defines_local_situation_editor_contract(tmp_path: Path) -> None:
    frame_manifest = tmp_path / "frames.json"
    frame_manifest.write_text("{}", encoding="utf-8")
    packet = build_situation_editor_packet(
        SOURCE,
        TRANSCRIPT,
        SHOTS,
        frame_manifest,
        POLICY,
        "Tập trước Jiro vừa gặp Rago.",
    )

    prompt = render_situation_editor_prompt(packet)
    normalized = prompt.casefold()

    assert "MAIN_PLOT | SUPPORTING_PLOT" in prompt
    assert "MAIN_ACTION | SUPPORTING_ACTION | DECORATIVE" in prompt
    assert "không giữ hành động chỉ vì đẹp" in normalized
    assert "sau mỗi khoảng lấy phải có khoảng nguồn bị bỏ" in normalized
    assert "situations.json" in prompt
    assert "narration_plan.json" in prompt
    assert "xử lý xong và khóa một tình huống" in normalized
    assert "Gemini Web" not in prompt


def test_packet_preserves_prior_context_without_inventing_it(tmp_path: Path) -> None:
    frame_manifest = tmp_path / "frames.json"
    frame_manifest.write_text("{}", encoding="utf-8")

    packet = build_situation_editor_packet(
        SOURCE, TRANSCRIPT, SHOTS, frame_manifest, POLICY, None
    )

    assert packet.prior_context == ""
    assert packet.required_outputs == ("situations.json", "narration_plan.json")
