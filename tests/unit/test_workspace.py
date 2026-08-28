from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.workspace import assert_inside_run, cleanup_run, create_job


def test_create_job_uses_anime_season_episode_hierarchy(tmp_path: Path) -> None:
    video = tmp_path / "episode.mp4"
    video.write_bytes(b"source")

    paths = create_job(tmp_path, "Frieren", 1, 2, video)

    assert paths.episode_dir == tmp_path / "Kho_Anime" / "Frieren" / "Mua_01" / "Tap_002"
    assert paths.temp_dir.parent == tmp_path / "Tam_dang_xu_ly"
    assert paths.source_video == video.resolve()
    assert video.exists()
    assert all(path.is_dir() for path in paths.episode_artifact_dirs)


def test_create_job_refuses_to_overwrite_an_existing_final(tmp_path: Path) -> None:
    video = tmp_path / "episode.mp4"
    video.write_bytes(b"source")
    paths = create_job(tmp_path, "Frieren", 1, 2, video)
    (paths.final_dir / "review.mp4").write_bytes(b"final")

    with pytest.raises(MvpError, match="refuses to overwrite"):
        create_job(tmp_path, "Frieren", 1, 2, video)


def test_cleanup_rejects_any_target_outside_exact_run(tmp_path: Path) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-1"
    run.mkdir(parents=True)

    with pytest.raises(MvpError, match="outside"):
        assert_inside_run(tmp_path / "Kho_Anime", run)


def test_cleanup_removes_only_run_and_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    run = tmp_path / "Tam_dang_xu_ly" / "run-1"
    nested = run / "proxy" / "clip.bin"
    nested.parent.mkdir(parents=True)
    nested.write_bytes(b"temporary")

    cleanup_run(run)

    assert not run.exists()
    assert source.read_bytes() == b"source"
