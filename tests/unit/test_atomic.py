from __future__ import annotations

import json
from pathlib import Path

import pytest

from anime_review_mvp.atomic import load_atomic_storyboard, load_critic_review
from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import (
    Event,
    Shot,
    SourceRegionAnnotation,
    TruthDocument,
)


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _truth(*, excluded: bool = False) -> TruthDocument:
    regions = (
        (SourceRegionAnnotation("region-001", 0, 1_000, "OPENING", "EXCLUDE", "Opening sequence."),)
        if excluded
        else ()
    )
    return TruthDocument(
        events=(
            Event(
                "event-001",
                1_000,
                4_000,
                ("Jiro",),
                "Jiro runs through the gate.",
                "MAIN_PLOT",
                1.0,
            ),
        ),
        source_regions=regions,
        source_region_scan_complete=True,
    )


def _shots() -> tuple[Shot, ...]:
    return (Shot("shot-001", 1_000, 2_500), Shot("shot-002", 2_500, 4_000))


def _payload() -> dict[str, object]:
    return {
        "owner": "ANTIGRAVITY",
        "policy_version": "atomic-v1",
        "producer_context_id": "producer-01",
        "claims": [
            {
                "claim_id": "claim-001",
                "kind": "ACTION",
                "text": "Jiro runs through the gate.",
                "evidence_event_ids": ["event-001"],
            }
        ],
        "beats": [
            {
                "beat_id": "beat-001",
                "scene_id": "scene-001",
                "event_ids": ["event-001"],
                "claim_ids": ["claim-001"],
                "source_ranges": [
                    {
                        "range_id": "range-001",
                        "source_start_ms": 1_000,
                        "source_end_ms": 4_000,
                        "scene_id": "scene-001",
                        "beat_id": "beat-001",
                        "shot_ids": ["shot-001", "shot-002"],
                        "event_ids": ["event-001"],
                        "short_action_exception": False,
                    }
                ],
                "visual_fact": "Jiro chạy qua cổng.",
                "characters_visible": ["Jiro"],
                "characters_spoken_about": ["Jiro"],
                "sync_mode": "ACTION",
                "action_window_start_ms": 1_100,
                "action_window_end_ms": 2_800,
                "narration_text": "Jiro lao qua cổng như đang bị deadline dí.",
                "frame_evidence": ["shot-001.jpg", "shot-002.jpg"],
                "estimated_tts_ms": 3_000,
                "actual_tts_ms": None,
                "tts_cache_key": "",
                "status": "LOCKED",
                "finding_codes": [],
            }
        ],
    }


def test_atomic_storyboard_accepts_many_shots_for_one_action(tmp_path: Path) -> None:
    document = load_atomic_storyboard(
        _write(tmp_path / "atomic.json", _payload()), _truth(), _shots(), 10_000
    )

    assert document.owner == "ANTIGRAVITY"
    assert document.beats[0].source_ranges[0].shot_ids == ("shot-001", "shot-002")


def test_atomic_storyboard_rejects_action_window_outside_footage(tmp_path: Path) -> None:
    payload = _payload()
    beats = payload["beats"]
    assert isinstance(beats, list)
    beats[0]["action_window_start_ms"] = 900

    with pytest.raises(MvpError, match="action window"):
        load_atomic_storyboard(
            _write(tmp_path / "atomic.json", payload), _truth(), _shots(), 10_000
        )


def test_context_beat_rejects_action_window(tmp_path: Path) -> None:
    payload = _payload()
    beats = payload["beats"]
    assert isinstance(beats, list)
    beats[0]["sync_mode"] = "CONTEXT"

    with pytest.raises(MvpError, match="CONTEXT"):
        load_atomic_storyboard(
            _write(tmp_path / "atomic.json", payload), _truth(), _shots(), 10_000
        )


def test_atomic_storyboard_rejects_excluded_footage(tmp_path: Path) -> None:
    payload = _payload()
    beats = payload["beats"]
    assert isinstance(beats, list)
    beats[0]["source_ranges"][0]["source_start_ms"] = 500

    with pytest.raises(MvpError, match="excluded"):
        load_atomic_storyboard(
            _write(tmp_path / "atomic.json", payload), _truth(excluded=True), _shots(), 10_000
        )


def test_atomic_storyboard_rejects_frame_evidence_outside_selected_shots(
    tmp_path: Path,
) -> None:
    payload = _payload()
    beats = payload["beats"]
    assert isinstance(beats, list)
    beats[0]["frame_evidence"] = ["shot-999.jpg"]

    with pytest.raises(MvpError, match="frame evidence.*selected shot"):
        load_atomic_storyboard(
            _write(tmp_path / "atomic.json", payload), _truth(), _shots(), 10_000
        )


def test_atomic_storyboard_rejects_short_action_window_for_long_voice(
    tmp_path: Path,
) -> None:
    payload = _payload()
    beats = payload["beats"]
    assert isinstance(beats, list)
    beats[0]["estimated_tts_ms"] = 9_000
    beats[0]["action_window_start_ms"] = 1_000
    beats[0]["action_window_end_ms"] = 2_000

    with pytest.raises(MvpError, match="action window.*TTS"):
        load_atomic_storyboard(
            _write(tmp_path / "atomic.json", payload), _truth(), _shots(), 10_000
        )


def test_atomic_storyboard_rejects_voice_leading_action_by_more_than_750ms(
    tmp_path: Path,
) -> None:
    payload = _payload()
    beats = payload["beats"]
    assert isinstance(beats, list)
    beats[0]["action_window_start_ms"] = 1_800
    beats[0]["action_window_end_ms"] = 3_500

    with pytest.raises(MvpError, match="voice leads action"):
        load_atomic_storyboard(
            _write(tmp_path / "atomic.json", payload), _truth(), _shots(), 10_000
        )


def test_critic_review_rejects_self_review_and_pass_field(tmp_path: Path) -> None:
    storyboard = load_atomic_storyboard(
        _write(tmp_path / "atomic.json", _payload()), _truth(), _shots(), 10_000
    )
    review = {
        "phase": "SCRIPT",
        "producer_context_id": "producer-01",
        "critic_context_id": "producer-01",
        "beat_reviews": [
            {
                "beat_id": "beat-001",
                "finding_codes": [],
                "evidence_refs": ["frame-1100.jpg"],
                "note": "Khớp hình và sự thật.",
            }
        ],
    }
    with pytest.raises(MvpError, match="separate"):
        load_critic_review(_write(tmp_path / "review.json", review), storyboard, "SCRIPT")

    review["critic_context_id"] = "critic-01"
    review["passed"] = True
    with pytest.raises(MvpError, match="fields"):
        load_critic_review(_write(tmp_path / "review.json", review), storyboard, "SCRIPT")
