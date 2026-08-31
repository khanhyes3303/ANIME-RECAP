from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from anime_review_mvp import cli
from anime_review_mvp.cli import main
from anime_review_mvp.errors import MvpError
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


def test_cli_exposes_editor_and_proxy_commands() -> None:
    parser = cli._parser()
    assert parser.parse_args(
        ["migrate-run", "--run", "run", "--reason", "user-rejected"]
    ).command == "migrate-run"
    assert parser.parse_args(["operator", "--run", "run"]).command == "operator"
    assert parser.parse_args(["editor-task", "--run", "run"]).command == "editor-task"
    assert parser.parse_args(["approve-proxy", "--run", "run"]).command == "approve-proxy"
    assert parser.parse_args(
        [
            "reject-proxy", "--run", "run", "--note", "Voice sớm",
            "--situation", "situation-004",
        ]
    ).command == "reject-proxy"


def test_cli_final_render_refuses_unapproved_v2_proxy(tmp_path: Path) -> None:
    run = tmp_path / "run"
    episode = tmp_path / "episode"
    episode.mkdir()
    new_state(run, stage=Stage.DUNG_VIDEO_CUOI, episode_dir=episode)
    state_path = run / "run_state.json"
    raw = json.loads(state_path.read_text(encoding="utf-8"))
    raw["editorial_revision"] = 2
    state_path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(MvpError, match="proxy approval"):
        cli._render(run, "final")


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


def test_operator_command_prepares_structure_job_after_local_prepare(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    episode = tmp_path / "episode"
    source = tmp_path / "episode.mp4"
    episode.mkdir()
    source.write_bytes(b"source")
    new_state(run, stage=Stage.CHUAN_BI, episode_dir=episode, source_video=source)

    def fake_prepare(path: Path) -> int:
        assert path == run
        new_state(
            run,
            stage=Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG,
            episode_dir=episode,
            source_video=source,
        )
        cli._write_next(run, "Chuẩn bị xong; tạo job structure.")
        return 0

    def fake_structure_task(path: Path) -> int:
        assert path == run
        cli._write_next(run, "Antigravity xử lý structure.")
        return 0

    monkeypatch.setattr(cli, "_prepare", fake_prepare)
    monkeypatch.setattr(cli, "_structure_task_command", fake_structure_task)

    assert cli._operator_command(run) == 0

    payload = json.loads((run / "operator_status.json").read_text(encoding="utf-8"))
    assert payload["action"] == "PREPARE_STRUCTURE_JOB"
    assert payload["stage"] == "PHAN_TICH"
    assert "public_stage" not in payload
    assert payload["instruction"] == "Antigravity xử lý structure."
    assert payload["antigravity_work_required"] is True


def test_operator_does_not_duplicate_an_already_prepared_situation_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    new_state(run, stage=Stage.CHO_ANTIGRAVITY_TINH_HUONG)
    raw_state = json.loads((run / "run_state.json").read_text(encoding="utf-8"))
    raw_state.update(
        {
            "current_situation_id": "situation-001",
            "editor_task_id": "situation-001-revision-002",
        }
    )
    (run / "run_state.json").write_text(
        json.dumps(raw_state), encoding="utf-8"
    )
    (run / "situation_index.json").write_text(
        json.dumps({"situations": [{"situation_id": "situation-001"}]}),
        encoding="utf-8",
    )
    cli._write_next(run, "Đang chờ Antigravity hoàn tất task hiện tại.")

    def duplicate(_run: Path) -> int:
        raise AssertionError("operator created a duplicate editor task")

    monkeypatch.setattr(cli, "_editor_task_command", duplicate)

    assert cli._operator_command(run) == 0
    payload = json.loads((run / "operator_status.json").read_text(encoding="utf-8"))
    assert payload["action"] == "PREPARE_SITUATION_JOB"
    assert payload["task_id"] == "situation-001-revision-002"


def test_operator_status_marks_user_gate_without_antigravity_work(
    tmp_path: Path,
) -> None:
    run = tmp_path / "run"
    new_state(run, stage=Stage.CHO_NGUOI_DUNG_DUYET_PROXY)
    cli._write_next(run, "Proxy sẵn sàng; chờ người dùng duyệt.")

    assert cli._operator_command(run) == 0
    payload = json.loads((run / "operator_status.json").read_text(encoding="utf-8"))
    assert payload["action"] == "WAIT_FOR_USER_PROXY_APPROVAL"
    assert payload["antigravity_work_required"] is False


def test_operator_drives_local_stages_until_verifier_handoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = tmp_path / "run"
    new_state(run, stage=Stage.KIEM_DINH_TINH_HUONG)
    calls: list[str] = []

    def set_stage(stage: Stage) -> None:
        raw = json.loads((run / "run_state.json").read_text(encoding="utf-8"))
        raw["stage"] = stage.value
        (run / "run_state.json").write_text(json.dumps(raw), encoding="utf-8")

    def fake_audit(_run: Path, phase: str, _review: object) -> int:
        calls.append(f"audit:{phase}")
        state = read_state(run)
        if state.stage is Stage.KIEM_DINH_TINH_HUONG:
            set_stage(Stage.TAO_TTS_TINH_HUONG)
        else:
            set_stage(Stage.CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG)
        return 0

    def fake_tts(_run: Path, _situation: str) -> int:
        calls.append("tts")
        set_stage(Stage.LAP_TIMELINE_TINH_HUONG)
        return 0

    def fake_timeline(_run: Path, _situation: str) -> int:
        calls.append("timeline")
        set_stage(Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG)
        return 0

    def fake_verifier(_run: Path, kind: str) -> int:
        calls.append(f"verifier:{kind}")
        raw = json.loads((run / "run_state.json").read_text(encoding="utf-8"))
        raw["verifier_task_id"] = "situation-001-audit-001"
        (run / "run_state.json").write_text(json.dumps(raw), encoding="utf-8")
        return 0

    monkeypatch.setattr(cli, "_audit", fake_audit)
    monkeypatch.setattr(cli, "_tts", fake_tts)
    monkeypatch.setattr(cli, "_timeline_command", fake_timeline)
    monkeypatch.setattr(cli, "_verifier_task_command", fake_verifier)

    assert cli._operator_command(run) == 0
    assert calls == ["audit:situation", "tts", "timeline", "audit:situation", "verifier:situation"]
    assert read_state(run).stage is Stage.CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG
