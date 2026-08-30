from __future__ import annotations

import json
from dataclasses import replace
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
    _write_json(
        run / "atomic_evidence/source/anchors.json",
        {
            "anchors": [
                {
                    "anchor_id": "beat-001-range-001-start",
                    "span_id": "beat-001",
                    "range_id": "range-001",
                    "timeline": "SOURCE",
                    "position": "START",
                    "timestamp_ms": 1_000,
                    "path": "frame-start.jpg",
                }
            ]
        },
    )
    _write_json(
        run / "atomic_evidence/program/anchors.json",
        {
            "anchors": [
                {
                    "anchor_id": "beat-001-range-001-program-start",
                    "span_id": "beat-001",
                    "range_id": "range-001",
                    "timeline": "PROGRAM",
                    "position": "START",
                    "timestamp_ms": 0,
                    "path": "frame-program-start.jpg",
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


def test_script_packet_uploads_engine_anchor_ids(tmp_path: Path) -> None:
    run = _packet_fixture(tmp_path, "SCRIPT")

    packet = build_browser_packet(run, "SCRIPT", runner=_fake_ffmpeg)

    assert "anchors.json" in {Path(path).name for path in packet.upload_paths}


@pytest.mark.parametrize("phase", ("PROXY", "FINAL"))
def test_video_packet_uploads_full_source_candidate_mapping_and_both_timelines(
    tmp_path: Path,
    phase: str,
) -> None:
    run = _packet_fixture(tmp_path, phase)

    packet = build_browser_packet(run, phase, runner=_fake_ffmpeg)

    upload_names = {Path(path).name for path in packet.upload_paths}
    candidate_name = "proxy_review.mp4" if phase == "PROXY" else "final_candidate.mp4"
    assert upload_names == {
        "source_episode.mp4",
        candidate_name,
        "mapping.json",
        "source_anchors.json",
        "program_anchors.json",
        "manifest.json",
    }
    assert (Path(packet.manifest_path).parent / "source_episode.mp4").read_bytes() == (
        b"source-video"
    )
    prompt = Path(packet.prompt_path).read_text(encoding="utf-8")
    assert '"phase":"VIDEO"' in prompt
    assert "source_episode.mp4 là video tập gốc đầy đủ" in prompt
    assert f"{candidate_name} là video cần kiểm định" in prompt
    assert "source_anchors.json" in prompt
    assert "program_anchors.json" in prompt
    assert "TOÀN BỘ anchor_id START/MIDDLE/END của cả SOURCE và PROGRAM" in prompt


@pytest.mark.parametrize(
    ("missing", "message"),
    (
        ("source", "source anchors are missing"),
        ("program", "program anchors are missing"),
    ),
)
def test_video_packet_fails_closed_when_timeline_anchors_are_missing(
    tmp_path: Path,
    missing: str,
    message: str,
) -> None:
    run = _packet_fixture(tmp_path, "PROXY")
    (run / "atomic_evidence" / missing / "anchors.json").unlink()

    with pytest.raises(MvpError, match=message):
        build_browser_packet(run, "PROXY", runner=_fake_ffmpeg)


def test_packet_detects_file_changed_after_manifest(tmp_path: Path) -> None:
    run = _packet_fixture(tmp_path, "PROXY")
    packet = build_browser_packet(run, "PROXY", runner=_fake_ffmpeg)
    Path(packet.media_path).write_bytes(b"tampered")

    with pytest.raises(MvpError, match="hash"):
        verify_packet(packet, run)


def test_packet_rejects_upload_set_that_omits_manifest_content(tmp_path: Path) -> None:
    run = _packet_fixture(tmp_path, "PROXY")
    packet = build_browser_packet(run, "PROXY", runner=_fake_ffmpeg)
    incomplete = replace(
        packet,
        upload_paths=tuple(
            path for path in packet.upload_paths if Path(path).name != "program_anchors.json"
        ),
    )

    with pytest.raises(MvpError, match="upload set is incomplete"):
        verify_packet(incomplete, run)


def test_packet_rejects_unknown_requested_beat(tmp_path: Path) -> None:
    run = _packet_fixture(tmp_path, "SCRIPT")

    with pytest.raises(MvpError, match="beat"):
        build_browser_packet(
            run,
            "SCRIPT",
            beat_ids=("beat-999",),
            runner=_fake_ffmpeg,
        )


def test_prompt_spells_out_exact_critic_json_contract(tmp_path: Path) -> None:
    run = _packet_fixture(tmp_path, "SCRIPT")

    packet = build_browser_packet(run, "SCRIPT", runner=_fake_ffmpeg)
    prompt = Path(packet.prompt_path).read_text(encoding="utf-8")

    for required_field in (
        '"critic_context_id"',
        '"observed_visual"',
        '"narration_summary"',
        '"note"',
    ):
        assert required_field in prompt
    assert '"overall_verdict"' not in prompt
    assert '"sync_verdict":"NOT_APPLICABLE"' in prompt
    assert "anchor_id" in prompt
