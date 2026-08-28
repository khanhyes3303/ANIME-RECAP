from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from anime_review_mvp.cli import main


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
