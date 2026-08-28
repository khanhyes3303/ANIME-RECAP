from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path
from zipfile import ZipFile

import pytest

from anime_review_mvp import cli
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.models import (
    TranscriptDocument,
    TtsCue,
    TtsManifest,
)
from anime_review_mvp.render import render_review
from anime_review_mvp.workflow import Stage, read_state


def _make_source(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:d=8",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=8",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
    )


def _fake_transcribe(video: Path, output: Path, **_: object) -> TranscriptDocument:
    assert video.is_file()
    document = TranscriptDocument(language="en", segments=())
    dump_json(output, document)
    return document


def _fake_tts(script: object, output_dir: Path, **_: object) -> TtsManifest:
    del script
    output_dir.mkdir(parents=True, exist_ok=True)
    mp3 = output_dir / "cue-001.mp3"
    wav = output_dir / "cue-001.wav"
    narration = output_dir / "narration.wav"
    mp3.write_bytes(b"fixture")
    for path in (wav, narration):
        with wave.open(str(path), "wb") as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(24_000)
            target.writeframes(b"\0\0" * 24_000 * 8)
    manifest = TtsManifest(
        (TtsCue("cue-001", str(mp3), str(wav), 8_000),),
        str(narration),
        "fake",
        "BV074_streaming",
    )
    dump_json(output_dir / "tts_manifest.json", manifest)
    return manifest


def _short_render(*args: object, **kwargs: object):
    return render_review(*args, **kwargs, allow_short_fixture=True)


def test_one_episode_reaches_package_without_network_or_real_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "transcribe_english", _fake_transcribe)
    monkeypatch.setattr(cli, "synthesize_script", _fake_tts)
    monkeypatch.setattr(cli, "render_review", _short_render)
    source = tmp_path / "episode.mp4"
    _make_source(source)

    assert cli.main(
        [
            "start",
            "--anime",
            "Anime Test",
            "--season",
            "1",
            "--episode",
            "1",
            "--video",
            str(source),
        ]
    ) == 0
    run = next((tmp_path / "Tam_dang_xu_ly").iterdir())
    episode = Path(read_state(run).episode_dir)
    assert cli.main(["prepare", "--run", str(run)]) == 0

    fixtures = Path(__file__).parents[1] / "fixtures" / "operator_artifacts"
    copies = {
        "su_that_tap_phim.json": episode / "Su_that" / "su_that_tap_phim.json",
        "scene_packets.json": episode / "Su_that" / "scene_packets.json",
        "kich_ban_review.json": episode / "Kich_ban" / "kich_ban_review.json",
        "edl.json": episode / "Ke_hoach_canh" / "edl.json",
        "kiem_dinh.json": episode / "Bao_cao" / "kiem_dinh.json",
    }
    for name, destination in copies.items():
        shutil.copy2(fixtures / name, destination)

    assert cli.main(["validate", "--run", str(run), "--artifact", "truth"]) == 0
    assert cli.main(["validate", "--run", str(run), "--artifact", "scene"]) == 0
    assert cli.main(["validate", "--run", str(run), "--artifact", "script"]) == 0
    assert cli.main(["audit", "--run", str(run), "--phase", "script"]) == 0
    assert cli.main(["tts", "--run", str(run)]) == 0
    generated_edl = json.loads(
        (episode / "Ke_hoach_canh" / "edl.json").read_text(encoding="utf-8")
    )
    assert generated_edl["segments"][0]["scene_id"] == "scene-001"
    assert generated_edl["segments"][0]["beat_id"] == "beat-001"
    assert cli.main(["validate", "--run", str(run), "--artifact", "edl"]) == 0
    assert cli.main(["render", "--run", str(run)]) == 0
    assert cli.main(["audit", "--run", str(run), "--phase", "video"]) == 0
    assert cli.main(["package", "--run", str(run)]) == 0

    archive = next((tmp_path / "Goi_gui_ChatGPT_Web").glob("*.zip"))
    with ZipFile(archive) as zipped:
        state_payload = zipped.read("run_state.json").decode("utf-8")
    assert f'"stage": "{Stage.HOAN_THANH.value}"' in state_payload
    assert not run.exists()
    assert next((episode / "Thanh_pham").glob("*.mp4")).is_file()
