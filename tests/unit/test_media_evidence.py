from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from anime_review_mvp import media
from anime_review_mvp.errors import MvpError
from anime_review_mvp.media import classify_edge_frame, evidence_timestamps, preflight_media_tools
from anime_review_mvp.models import Shot, TranscriptDocument, TranscriptSegment


def _image(path: Path, color: tuple[int, int, int]) -> Path:
    Image.new("RGB", (16, 16), color).save(path)
    return path


def test_preflight_names_every_missing_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media.shutil, "which", lambda _name: None)

    with pytest.raises(MvpError, match="ffmpeg, ffprobe"):
        preflight_media_tools()


def test_preflight_returns_resolved_existing_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media.shutil, "which", lambda name: f"C:/tools/{name}.exe")

    assert preflight_media_tools() == (
        Path("C:/tools/ffmpeg.exe"),
        Path("C:/tools/ffprobe.exe"),
    )


def test_evidence_timestamps_include_subtitle_and_shot_boundaries() -> None:
    shots = (Shot("shot-001", 0, 900), Shot("shot-002", 1_000, 2_000))
    transcript = TranscriptDocument(
        language="en",
        segments=(TranscriptSegment(1_000, 2_000, "Jiro fights back.", ()),),
    )

    assert evidence_timestamps(shots, transcript) == (0, 900, 1_000, 1_500, 2_000)


def test_edge_frame_classifies_black_flash_and_content(tmp_path: Path) -> None:
    assert classify_edge_frame(_image(tmp_path / "black.png", (0, 0, 0))) == "BLACK"
    assert classify_edge_frame(_image(tmp_path / "flash.png", (255, 255, 255))) == "FLASH"
    assert classify_edge_frame(_image(tmp_path / "content.png", (90, 130, 180))) == "CONTENT"


def test_short_isolated_visual_jump_is_transition(tmp_path: Path) -> None:
    previous = _image(tmp_path / "previous.png", (40, 40, 40))
    current = _image(tmp_path / "current.png", (180, 50, 50))
    following = _image(tmp_path / "following.png", (40, 40, 40))

    assert (
        classify_edge_frame(
            current,
            previous_path=previous,
            next_path=following,
            persistence_ms=100,
        )
        == "TRANSITION"
    )
    assert (
        classify_edge_frame(
            current,
            previous_path=previous,
            next_path=following,
            persistence_ms=500,
        )
        == "CONTENT"
    )
