from __future__ import annotations

import json
from pathlib import Path

import pytest

from anime_review_mvp import cli
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.models import (
    AtomicBeat,
    AtomicStoryboard,
    Claim,
    Event,
    Shot,
    ShotDocument,
    SourceRef,
    SpanSourceRange,
    TranscriptDocument,
    TruthDocument,
)
from anime_review_mvp.workflow import Stage, new_state, read_state


def _prepared_storyboard_run(tmp_path: Path) -> tuple[Path, Path]:
    episode = tmp_path / "Kho_Anime" / "A" / "Mua_01" / "Tap_001"
    for name in (
        "Dau_vao",
        "Su_that",
        "Kich_ban",
        "TTS",
        "Ke_hoach_canh",
        "Thanh_pham",
        "Bao_cao",
        "_Cache",
    ):
        (episode / name).mkdir(parents=True, exist_ok=True)
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"source")
    run = tmp_path / "Tam_dang_xu_ly" / "run"
    new_state(run, stage=Stage.LAP_STORYBOARD, episode_dir=episode, source_video=source)
    dump_json(
        episode / "Dau_vao" / "source_ref.json",
        SourceRef(str(source), "a" * 64, 10_000, 320, 180, "1/1000", 1),
    )
    dump_json(
        episode / "Su_that" / "su_that_tap_phim.json",
        TruthDocument(
            (Event("event-001", 1_000, 4_000, ("Jiro",), "Jiro runs.", "MAIN", 1.0),),
            (),
            True,
        ),
    )
    dump_json(run / "shots.json", ShotDocument((Shot("shot-001", 1_000, 4_000),)))
    dump_json(
        episode / "Kich_ban" / "atomic_storyboard.json",
        AtomicStoryboard(
            "ANTIGRAVITY",
            "atomic-v1",
            "producer-01",
            (Claim("claim-001", "ACTION", "Jiro runs.", ("event-001",)),),
            (
                AtomicBeat(
                    "beat-001",
                    "scene-001",
                    ("event-001",),
                    ("claim-001",),
                    (
                        SpanSourceRange(
                            "range-001",
                            1_000,
                            4_000,
                            "scene-001",
                            "beat-001",
                            ("shot-001",),
                            ("event-001",),
                        ),
                    ),
                    "Jiro chạy.",
                    ("Jiro",),
                    ("Jiro",),
                    "ACTION",
                    1_000,
                    2_000,
                    "Jiro lao vào sân.",
                    ("frame-1000.jpg",),
                    3_000,
                    None,
                    "",
                    "LOCKED",
                    (),
                ),
            ),
        ),
    )
    return run, episode


def test_cli_validates_storyboard_without_waiting_for_codex(tmp_path: Path) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)

    assert cli.main(["validate", "--run", str(run), "--artifact", "storyboard"]) == 0

    assert read_state(run).stage is Stage.VIET_LOI
    instruction = json.loads((run / "next_action.json").read_text(encoding="utf-8"))["instruction"]
    assert "Antigravity" in instruction
    assert "Codex" not in instruction


def test_render_parser_accepts_explicit_proxy_quality() -> None:
    args = cli._parser().parse_args(["render", "--run", "run", "--quality", "proxy"])
    assert args.quality == "proxy"


def test_prepare_reuses_source_analysis_for_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"source")
    calls = {"transcript": 0, "shots": 0, "frames": 0}
    monkeypatch.setattr(
        cli,
        "probe_source",
        lambda path: SourceRef(str(path), "a" * 64, 10_000, 320, 180, "1/1000", 1),
    )

    def transcribe(video: Path, output: Path) -> TranscriptDocument:
        calls["transcript"] += 1
        result = TranscriptDocument("en", ())
        dump_json(output, result)
        return result

    def shots(video: Path, duration: int) -> tuple[Shot, ...]:
        calls["shots"] += 1
        return (Shot("shot-0001", 0, duration),)

    def frames(video: Path, detected: tuple[Shot, ...], output: Path) -> tuple[Path, ...]:
        calls["frames"] += 1
        output.mkdir(parents=True, exist_ok=True)
        frame = output / "shot-0001.jpg"
        frame.write_bytes(b"frame")
        return (frame,)

    monkeypatch.setattr(cli, "transcribe_english", transcribe)
    monkeypatch.setattr(cli, "detect_shots", shots)
    monkeypatch.setattr(cli, "extract_inspection_assets", frames)

    command = ["start", "--anime", "A", "--season", "1", "--episode", "1", "--video", str(source)]
    assert cli.main(command) == 0
    first_run = next((tmp_path / "Tam_dang_xu_ly").iterdir())
    assert cli.main(["prepare", "--run", str(first_run)]) == 0
    assert cli.main([*command, "--revision"]) == 0
    second_run = next(path for path in (tmp_path / "Tam_dang_xu_ly").iterdir() if path != first_run)
    assert cli.main(["prepare", "--run", str(second_run)]) == 0

    assert calls == {"transcript": 1, "shots": 1, "frames": 1}
