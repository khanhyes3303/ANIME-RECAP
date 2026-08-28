from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from anime_review_mvp.package import create_handoff_zip, finalize_run
from anime_review_mvp.workflow import Stage, new_state


def _completed_run(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    episode = tmp_path / "Kho_Anime" / "A" / "Mua_01" / "Tap_001"
    files = {
        "Su_that/su_that_tap_phim.json": {"events": []},
        "Kich_ban/kich_ban_review.json": {"cues": []},
        "TTS/tts_manifest.json": {"cues": []},
        "Ke_hoach_canh/edl.json": {"segments": []},
        "Bao_cao/kiem_dinh.json": {"passed": True},
    }
    for relative, payload in files.items():
        path = episode / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
    final = episode / "Thanh_pham" / "review.mp4"
    final.parent.mkdir(parents=True)
    final.write_bytes(b"final-video")
    run = tmp_path / "Tam_dang_xu_ly" / "run-001"
    new_state(
        run,
        stage=Stage.DONG_GOI,
        episode_dir=episode,
        source_video=source,
    )
    return run, source, final


def test_zip_contains_reports_but_no_video_bytes(tmp_path: Path) -> None:
    run, _, _ = _completed_run(tmp_path)

    archive = create_handoff_zip(run, tmp_path / "handoff.zip")

    with ZipFile(archive) as zipped:
        names = set(zipped.namelist())
        report = json.loads(zipped.read("bao_cao.json"))
    assert {
        "bao_cao.md",
        "bao_cao.json",
        "kich_ban_review.json",
        "edl.json",
        "run_state.json",
    } <= names
    assert not any(name.endswith((".mp4", ".mkv")) for name in names)
    assert len(report["source"]["sha256"]) == 64
    assert len(report["final"]["sha256"]) == 64


def test_finalize_preserves_source_and_episode_artifacts(tmp_path: Path) -> None:
    run, source, final = _completed_run(tmp_path)

    result = finalize_run(run, passed=True)

    assert source.exists()
    assert final.exists()
    assert result.archive.exists()
    assert result.status == "PASS"
    assert not run.exists()


def test_human_required_run_packages_without_a_final_video(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    episode = tmp_path / "Kho_Anime" / "A" / "Mua_01" / "Tap_002"
    (episode / "Bao_cao").mkdir(parents=True)
    run = tmp_path / "Tam_dang_xu_ly" / "run-002"
    new_state(
        run,
        stage=Stage.CAN_CON_NGUOI_XU_LY,
        episode_dir=episode,
        source_video=source,
    )

    result = finalize_run(run, passed=False)

    with ZipFile(result.archive) as zipped:
        report = json.loads(zipped.read("bao_cao.json"))
    assert result.status == "CAN_CON_NGUOI_XU_LY"
    assert report["final"] is None
    assert not run.exists()
