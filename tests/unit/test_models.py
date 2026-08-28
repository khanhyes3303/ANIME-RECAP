from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.jsonio import dump_json, load_json
from anime_review_mvp.models import (
    Claim,
    Event,
    NarrationCue,
    SceneBeat,
    ScenePacket,
    ScenePacketDocument,
    SceneShot,
    ScriptDocument,
)


def test_event_rejects_an_interval_that_runs_backwards() -> None:
    with pytest.raises(MvpError, match="event interval"):
        Event("E001", 2_000, 1_000, ("A",), "sai", "CORE", 1.0)


def test_claim_rejects_missing_factual_evidence() -> None:
    with pytest.raises(MvpError, match="factual evidence"):
        Claim("C001", "ACTION", "A chạy", ())


def test_script_round_trip_preserves_vietnamese_text_and_tuples(tmp_path: Path) -> None:
    script = ScriptDocument(
        (
            NarrationCue(
                "N001",
                "Cậu này chạy như bị dí KPI.",
                ("C001",),
                ("E001",),
                True,
            ),
        )
    )
    path = tmp_path / "script.json"

    dump_json(path, script)

    assert load_json(path, ScriptDocument) == script
    assert "dí KPI" in path.read_text(encoding="utf-8")


def test_scene_packet_round_trip_preserves_many_shots_and_beats(tmp_path: Path) -> None:
    packet = ScenePacket(
        scene_id="scene-001",
        start_ms=1_000,
        end_ms=8_000,
        story_purpose="Nhân vật bắt đầu cuộc giao chiến.",
        event_ids=("event-001", "event-002"),
        shots=(
            SceneShot("shot-001", 1_000, 3_000, "MUST_KEEP", ("event-001",), "Mở cảnh"),
            SceneShot("shot-002", 3_000, 5_000, "OPTIONAL", ("event-001",), "Nhịp chuyển"),
            SceneShot("shot-003", 5_000, 8_000, "MUST_KEEP", ("event-002",), "Kết quả đòn đánh"),
        ),
        beats=(
            SceneBeat(
                "beat-001",
                1_000,
                5_000,
                ("event-001",),
                ("shot-001", "shot-002"),
                ("cue-001",),
            ),
            SceneBeat("beat-002", 5_000, 8_000, ("event-002",), ("shot-003",), ("cue-001",)),
        ),
        cue_ids=("cue-001",),
    )
    path = tmp_path / "scene_packets.json"

    dump_json(path, packet)

    assert load_json(path, ScenePacket) == packet
    assert len(packet.shots) == 3
    assert packet.beats[1].shot_ids == ("shot-003",)


def test_scene_shot_rejects_unknown_role() -> None:
    with pytest.raises(MvpError, match="role"):
        SceneShot("shot-001", 0, 1_000, "KEEP_ALWAYS", (), "bad role")


def test_scene_packet_document_round_trip(tmp_path: Path) -> None:
    packet = ScenePacket(
        "scene-001",
        0,
        2_000,
        "Một scene ngắn.",
        ("event-001",),
        (SceneShot("shot-001", 0, 2_000, "MUST_KEEP", ("event-001",), "Chính"),),
        (SceneBeat("beat-001", 0, 2_000, ("event-001",), ("shot-001",), ("cue-001",)),),
        ("cue-001",),
    )
    document = ScenePacketDocument((packet,))
    path = tmp_path / "scene_packets.json"
    dump_json(path, document)
    assert load_json(path, ScenePacketDocument) == document
