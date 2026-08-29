from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.gemini_packets import (
    build_browser_packet,
    sha256_packet,
    verify_packet,
)
from anime_review_mvp.workflow import Stage, new_state


def _storyboard_payload() -> dict[str, object]:
    return {
        "owner": "ANTIGRAVITY",
        "policy_version": "atomic-v1",
        "producer_context_id": "producer-01",
        "claims": [
            {
                "claim_id": "claim-001",
                "kind": "ACTION",
                "text": "Jiro chạy qua cổng.",
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
                        "shot_ids": ["shot-001"],
                        "event_ids": ["event-001"],
                        "short_action_exception": False,
                    }
                ],
                "visual_fact": "Jiro chạy qua cổng.",
                "characters_visible": ["Jiro"],
                "characters_spoken_about": ["Jiro"],
                "sync_mode": "ACTION",
                "action_window_start_ms": 1_000,
                "action_window_end_ms": 4_000,
                "narration_text": "Jiro lao qua cổng như bị dí deadline.",
                "frame_evidence": ["frame-001"],
                "estimated_tts_ms": 3_000,
                "actual_tts_ms": None,
                "tts_cache_key": "",
                "status": "LOCKED",
                "finding_codes": [],
            }
        ],
    }


def _truth_payload(*, excluded: bool = False) -> dict[str, object]:
    return {
        "events": [
            {
                "event_id": "event-001",
                "start_ms": 1_000,
                "end_ms": 4_000,
                "characters": ["Jiro"],
                "description": "Jiro chạy qua cổng.",
                "importance": "MAIN_PLOT",
                "confidence": 1.0,
            }
        ],
        "source_regions": (
            [
                {
                    "region_id": "op-001",
                    "start_ms": 500,
                    "end_ms": 2_000,
                    "kind": "OPENING",
                    "decision": "EXCLUDE",
                    "reason": "Opening sequence.",
                }
            ]
            if excluded
            else []
        ),
        "source_region_scan_complete": True,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _packet_fixture(tmp_path: Path, phase: str, *, excluded: bool = False) -> Path:
    project = tmp_path / "project"
    episode = project / "Kho_Anime/BLACK TORCH/Mua_01/Tap_001"
    run = project / "Tam_dang_xu_ly/run-123"
    source = project / "source.mp4"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"source-video")
    _write_json(episode / "Kich_ban/atomic_storyboard.json", _storyboard_payload())
    _write_json(episode / "Su_that/su_that_tap_phim.json", _truth_payload(excluded=excluded))
    _write_json(
        episode / "Ke_hoach_canh/atomic_edl.json",
        {
            "segments": [
                {
                    "segment_id": "seg-001",
                    "span_id": "span-001",
                    "source_start_ms": 1_000,
                    "source_end_ms": 4_000,
                    "program_start_ms": 0,
                    "program_end_ms": 3_000,
                    "range_id": "range-001",
                    "scene_id": "scene-001",
                    "beat_id": "beat-001",
                    "shot_ids": ["shot-001"],
                    "event_ids": ["event-001"],
                    "short_action_exception": False,
                }
            ]
        },
    )
    new_state(run, stage=Stage.VIET_LOI, episode_dir=episode, source_video=source)
    if phase == "PROXY":
        candidate = run / "proxy/review_proxy.mp4"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_bytes(b"proxy-video")
    elif phase == "FINAL":
        (run / "final_candidate.mp4").write_bytes(b"final-video")
    return run


def _fake_ffmpeg(command: list[str], **_: object) -> SimpleNamespace:
    Path(command[-1]).write_bytes(b"script-evidence-video")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


@pytest.mark.parametrize(
    ("phase", "expected_media"),
    (
        ("SCRIPT", "script_evidence.mp4"),
        ("PROXY", "proxy_review.mp4"),
        ("FINAL", "final_candidate.mp4"),
    ),
)
def test_builds_hashed_phase_packet(
    tmp_path: Path,
    phase: str,
    expected_media: str,
) -> None:
    run = _packet_fixture(tmp_path, phase)

    packet = build_browser_packet(run, phase, runner=_fake_ffmpeg)

    assert Path(packet.media_path).name == expected_media
    assert packet.phase == phase
    assert packet.packet_sha256 == sha256_packet(packet)
    assert packet.beat_ids == ("beat-001",)
    assert all(Path(path).is_file() for path in packet.upload_paths)
    verify_packet(packet, run)


def test_script_packet_rejects_source_range_overlapping_opening(tmp_path: Path) -> None:
    run = _packet_fixture(tmp_path, "SCRIPT", excluded=True)

    with pytest.raises(MvpError, match="excluded source region"):
        build_browser_packet(run, "SCRIPT", runner=_fake_ffmpeg)


def test_packet_detects_file_changed_after_manifest(tmp_path: Path) -> None:
    run = _packet_fixture(tmp_path, "PROXY")
    packet = build_browser_packet(run, "PROXY", runner=_fake_ffmpeg)
    Path(packet.media_path).write_bytes(b"tampered")

    with pytest.raises(MvpError, match="hash"):
        verify_packet(packet, run)


def test_packet_rejects_unknown_requested_beat(tmp_path: Path) -> None:
    run = _packet_fixture(tmp_path, "SCRIPT")

    with pytest.raises(MvpError, match="beat"):
        build_browser_packet(
            run,
            "SCRIPT",
            beat_ids=("beat-999",),
            runner=_fake_ffmpeg,
        )
