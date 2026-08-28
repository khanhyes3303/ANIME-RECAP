from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from anime_review_mvp import cli
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.models import TranscriptDocument
from anime_review_mvp.workflow import Stage, read_state


def _make_source(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=8",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
            "-shortest", "-c:v", "libx264", "-c:a", "aac", str(path),
        ],
        check=True,
    )


def _fake_transcribe(video: Path, output: Path, **_: object) -> TranscriptDocument:
    assert video.is_file()
    document = TranscriptDocument(language="en", segments=())
    dump_json(output, document)
    return document


def test_one_episode_hands_valid_draft_to_codex_without_packaging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "transcribe_english", _fake_transcribe)
    source = tmp_path / "episode.mp4"
    _make_source(source)

    assert cli.main(
        [
            "start", "--anime", "Anime Test", "--season", "1",
            "--episode", "1", "--video", str(source),
        ]
    ) == 0
    run = next((tmp_path / "Tam_dang_xu_ly").iterdir())
    episode = Path(read_state(run).episode_dir)
    assert cli.main(["prepare", "--run", str(run)]) == 0

    fixtures = Path(__file__).parents[1] / "fixtures" / "operator_artifacts"
    destinations = {
        "su_that_tap_phim.json": episode / "Su_that" / "su_that_tap_phim.json",
        "scene_packets.json": episode / "Su_that" / "scene_packets.json",
        "kich_ban_review.json": episode / "Kich_ban" / "kich_ban_review.json",
        "kiem_dinh.json": episode / "Bao_cao" / "kiem_dinh.json",
    }
    for name, destination in destinations.items():
        shutil.copy2(fixtures / name, destination)

    assert cli.main(["validate", "--run", str(run), "--artifact", "truth"]) == 0
    assert cli.main(["validate", "--run", str(run), "--artifact", "scene"]) == 0
    assert cli.main(["validate", "--run", str(run), "--artifact", "script"]) == 0
    assert cli.main(["audit", "--run", str(run), "--phase", "script"]) == 0

    assert read_state(run).stage is Stage.CODEX_BIEN_TAP
    assert run.is_dir()
    assert not (tmp_path / "Goi_gui_ChatGPT_Web").exists()
