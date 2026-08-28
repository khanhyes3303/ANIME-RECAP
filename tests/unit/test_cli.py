from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from anime_review_mvp.cli import main
from anime_review_mvp.workflow import Stage, new_state, read_state


def test_cli_start_accepts_exactly_one_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "ep.mp4"
    source.write_bytes(b"video")

    result = main(
        [
            "start",
            "--anime",
            "Frieren",
            "--season",
            "1",
            "--episode",
            "1",
            "--video",
            str(source),
        ]
    )

    assert result == 0
    assert list((tmp_path / "Tam_dang_xu_ly").glob("*/run_state.json"))


def test_cli_rejects_a_second_video_argument() -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "start",
                "--anime",
                "A",
                "--season",
                "1",
                "--episode",
                "1",
                "--video",
                "one.mp4",
                "two.mp4",
            ]
        )


def test_cli_help_is_printable_on_the_windows_cp1258_console() -> None:
    project_root = Path(__file__).parents[2]
    environment = {**os.environ, "PYTHONIOENCODING": "cp1258"}

    result = subprocess.run(
        [sys.executable, str(project_root / "run_episode.py"), "--help"],
        cwd=project_root,
        env=environment,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")


def test_start_revision_accepts_existing_final_without_replacing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"source")
    final = tmp_path / "Kho_Anime" / "A" / "Mua_01" / "Tap_001" / "Thanh_pham" / "review_anime.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"old")

    assert (
        main(
            [
                "start",
                "--anime",
                "A",
                "--season",
                "1",
                "--episode",
                "1",
                "--video",
                str(source),
                "--revision",
            ]
        )
        == 0
    )
    assert final.read_bytes() == b"old"


def test_script_audit_hands_draft_to_codex_editor(tmp_path: Path) -> None:
    episode = tmp_path / "Kho_Anime" / "A" / "Mua_01" / "Tap_001"
    report = episode / "Bao_cao" / "kiem_dinh.json"
    script = episode / "Kich_ban" / "kich_ban_review.json"
    report.parent.mkdir(parents=True)
    script.parent.mkdir(parents=True)
    report.write_text(
        json.dumps({"passed": True, "coverage_ratio": "1", "findings": []}),
        encoding="utf-8",
    )
    script.write_text(
        json.dumps(
            {
                "cues": [
                    {
                        "cue_id": "cue-001",
                        "text": "Jiro lao qua cổng.",
                        "claim_ids": ["claim-001"],
                        "event_ids": ["event-001"],
                        "directly_supported": True,
                        "scene_id": "scene-001",
                        "beat_ids": ["beat-001"],
                    }
                ],
                "claims": [
                    {
                        "claim_id": "claim-001",
                        "kind": "ACTION",
                        "text": "Jiro runs.",
                        "evidence_event_ids": ["event-001"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    run = tmp_path / "Tam_dang_xu_ly" / "run"
    new_state(run, stage=Stage.KIEM_DINH_KICH_BAN, episode_dir=episode)

    assert main(["audit", "--run", str(run), "--phase", "script"]) == 0
    assert read_state(run).stage is Stage.CODEX_BIEN_TAP
