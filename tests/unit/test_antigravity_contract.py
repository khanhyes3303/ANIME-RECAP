from __future__ import annotations

import json
from pathlib import Path

import pytest

from anime_review_mvp.antigravity import (
    build_operator_job,
    load_audit,
    load_scene_packets,
    load_script,
    load_truth,
)
from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import Shot, SourceRef, TranscriptDocument
from anime_review_mvp.workspace import create_job


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _truth_payload() -> dict[str, object]:
    return {
        "events": [
            {
                "event_id": "event-001",
                "start_ms": 1_000,
                "end_ms": 3_000,
                "characters": ["A"],
                "description": "A runs through the gate.",
                "importance": "MAIN_PLOT",
                "confidence": 0.95,
            }
        ],
        "source_regions": [
            {
                "region_id": "region-001",
                "start_ms": 0,
                "end_ms": 1_000,
                "kind": "OPENING",
                "decision": "EXCLUDE",
                "reason": "Visible title sequence.",
            }
        ],
        "source_region_scan_complete": True,
    }


def _script_payload() -> dict[str, object]:
    return {
        "claims": [
            {
                "claim_id": "claim-001",
                "kind": "ACTION",
                "text": "A runs through the gate.",
                "evidence_event_ids": ["event-001"],
            }
        ],
        "cues": [
            {
                "cue_id": "cue-001",
                "text": "A phi qua cổng như trễ deadline.",
                "claim_ids": ["claim-001"],
                "event_ids": ["event-001"],
                "directly_supported": True,
                "scene_id": "scene-001",
                "beat_ids": ["beat-001"],
            }
        ]
    }


def _scene_packets_payload() -> dict[str, object]:
    return {
        "packets": [
            {
                "scene_id": "scene-001",
                "start_ms": 1_000,
                "end_ms": 3_000,
                "story_purpose": "A chạy qua cổng.",
                "event_ids": ["event-001"],
                "shots": [
                    {
                        "shot_id": "shot-0001",
                        "start_ms": 1_000,
                        "end_ms": 3_000,
                        "role": "MUST_KEEP",
                        "event_ids": ["event-001"],
                        "reason": "Hành động chính.",
                    }
                ],
                "beats": [
                    {
                        "beat_id": "beat-001",
                        "start_ms": 1_000,
                        "end_ms": 3_000,
                        "event_ids": ["event-001"],
                        "shot_ids": ["shot-0001"],
                        "cue_ids": ["cue-001"],
                    }
                ],
                "cue_ids": ["cue-001"],
            }
        ]
    }


def _audit_payload(*, passed: bool = True) -> dict[str, object]:
    return {"passed": passed, "coverage_ratio": "1", "findings": []}


def test_truth_rejects_editorial_jokes(tmp_path: Path) -> None:
    payload = _truth_payload()
    events = payload["events"]
    assert isinstance(events, list)
    events[0]["editorial_joke"] = "thanh nien bao doi"

    with pytest.raises(MvpError, match="fields"):
        load_truth(_write(tmp_path / "truth.json", payload), source_duration_ms=10_000)


def test_truth_rejects_duplicate_ids_and_out_of_bounds_events(tmp_path: Path) -> None:
    payload = _truth_payload()
    events = payload["events"]
    assert isinstance(events, list)
    events.append(dict(events[0]))

    with pytest.raises(MvpError, match="duplicate"):
        load_truth(_write(tmp_path / "truth.json", payload), source_duration_ms=10_000)

    events.pop()
    events[0]["end_ms"] = 10_001
    with pytest.raises(MvpError, match="duration"):
        load_truth(_write(tmp_path / "truth.json", payload), source_duration_ms=10_000)


def test_script_requires_claim_and_event_binding(tmp_path: Path) -> None:
    payload = _script_payload()
    cues = payload["cues"]
    assert isinstance(cues, list)
    cues[0]["event_ids"] = []

    with pytest.raises(MvpError, match="claim and event"):
        load_script(_write(tmp_path / "script.json", payload))


def test_script_rejects_a_cue_bound_to_an_unknown_claim(tmp_path: Path) -> None:
    payload = _script_payload()
    cues = payload["cues"]
    assert isinstance(cues, list)
    cues[0]["claim_ids"] = ["claim-missing"]

    with pytest.raises(MvpError, match="unknown claim"):
        load_script(_write(tmp_path / "script.json", payload))


def test_script_requires_scene_and_beat_binding(tmp_path: Path) -> None:
    payload = _script_payload()
    cues = payload["cues"]
    assert isinstance(cues, list)
    cues[0].pop("scene_id")
    with pytest.raises(MvpError, match="fields"):
        load_script(_write(tmp_path / "script.json", payload))

    payload = _script_payload()
    cues = payload["cues"]
    assert isinstance(cues, list)
    cues[0]["scene_id"] = ""
    with pytest.raises(MvpError, match="scene_id"):
        load_script(_write(tmp_path / "script.json", payload))

    payload = _script_payload()
    cues = payload["cues"]
    assert isinstance(cues, list)
    cues[0]["beat_ids"] = []
    with pytest.raises(MvpError, match="beat_ids"):
        load_script(_write(tmp_path / "script.json", payload))


def test_audit_cannot_pass_with_contradiction(tmp_path: Path) -> None:
    payload = _audit_payload()
    payload["findings"] = [
        {
            "severity": "ERROR",
            "code": "FACT_CONTRADICTION",
            "cue_id": "cue-001",
            "message": "Wrong speaker.",
            "evidence_refs": ["event-001"],
        }
    ]

    with pytest.raises(MvpError, match="ERROR"):
        load_audit(_write(tmp_path / "audit.json", payload))


def test_truth_requires_completed_op_ed_scan(tmp_path: Path) -> None:
    payload = _truth_payload()
    payload["source_region_scan_complete"] = False

    with pytest.raises(MvpError, match="source-region"):
        load_truth(_write(tmp_path / "truth.json", payload), source_duration_ms=10_000)


def test_operator_job_points_to_only_one_episode_and_expected_outputs(
    tmp_path: Path,
) -> None:
    source_video = tmp_path / "episode.mp4"
    source_video.write_bytes(b"media")
    paths = create_job(tmp_path, "Anime A", 1, 2, source_video)
    source = SourceRef(str(source_video), "a" * 64, 10_000, 320, 180, "1/1000", 1)

    job_path = build_operator_job(
        paths,
        source,
        TranscriptDocument(language="en", segments=()),
        (Shot("shot-0001", 0, 10_000),),
    )

    payload = json.loads(job_path.read_text(encoding="utf-8"))
    assert payload["anime"] == "Anime A"
    assert payload["episode"] == 2
    assert payload["source"]["path"] == str(source_video)
    assert payload["required_outputs"] == {
        "truth": str(paths.truth_dir / "su_that_tap_phim.json"),
        "scene_packets": str(paths.truth_dir / "scene_packets.json"),
        "storyboard": str(paths.script_dir / "atomic_storyboard.json"),
        "critic_script": str(paths.report_dir / "critic_script.json"),
        "critic_video": str(paths.report_dir / "critic_video.json"),
    }
    assert len(payload["policy_sha256"]) == 64
    assert str(paths.truth_dir) in payload["write_policy"]["allowed_write_roots"]
    assert str(paths.tts_dir.resolve()) not in payload["write_policy"]["allowed_write_roots"]
    assert str(paths.edl_dir.resolve()) not in payload["write_policy"]["allowed_write_roots"]
    assert str(paths.final_dir.resolve()) not in payload["write_policy"]["allowed_write_roots"]
    assert str(source_video.resolve()) in payload["write_policy"]["read_only_roots"]
    assert str(paths.root / "Bo_nao_Antigravity") in payload["write_policy"]["read_only_roots"]
    assert "script" not in payload["required_outputs"]
    assert str(paths.script_dir / "khoa_cau_canh.json") in payload["write_policy"][
        "read_only_roots"
    ]
    assert str(paths.tts_dir.resolve()) in payload["write_policy"]["read_only_roots"]
    assert str(paths.edl_dir.resolve()) in payload["write_policy"]["read_only_roots"]
    assert str(paths.final_dir.resolve()) in payload["write_policy"]["read_only_roots"]
    assert str(paths.episode_dir / "Bao_cao_Codex") in payload["write_policy"][
        "read_only_roots"
    ]


def test_scene_packet_loader_rejects_extra_fields(tmp_path: Path) -> None:
    payload = _scene_packets_payload()
    packets = payload["packets"]
    assert isinstance(packets, list)
    packets[0]["unexpected"] = True
    with pytest.raises(MvpError, match="fields"):
        load_scene_packets(_write(tmp_path / "scene_packets.json", payload))
