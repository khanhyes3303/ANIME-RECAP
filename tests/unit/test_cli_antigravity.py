from __future__ import annotations

import json
from pathlib import Path

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
    TruthDocument,
)
from anime_review_mvp.workflow import Stage, new_state, read_state


def _prepared_storyboard_run(tmp_path: Path) -> tuple[Path, Path]:
    episode = tmp_path / "Kho_Anime" / "A" / "Mua_01" / "Tap_001"
    for name in ("Dau_vao", "Su_that", "Kich_ban", "TTS", "Ke_hoach_canh", "Thanh_pham", "Bao_cao", "_Cache"):
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
                    "beat-001", "scene-001", ("event-001",), ("claim-001",),
                    (SpanSourceRange("range-001", 1_000, 4_000, "scene-001", "beat-001", ("shot-001",), ("event-001",)),),
                    "Jiro chạy.", ("Jiro",), ("Jiro",), "ACTION", 1_000, 2_000,
                    "Jiro lao vào sân.", ("frame-1000.jpg",), 3_000, None, "", "LOCKED", (),
                ),
            ),
        ),
    )
    return run, episode


def test_cli_validates_storyboard_without_waiting_for_codex(tmp_path: Path) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)

    assert cli.main(["validate", "--run", str(run), "--artifact", "storyboard"]) == 0

    assert read_state(run).stage is Stage.VIET_LOI
    instruction = json.loads((run / "next_action.json").read_text(encoding="utf-8"))[
        "instruction"
    ]
    assert "Antigravity" in instruction
    assert "Codex" not in instruction


def test_render_parser_accepts_explicit_proxy_quality() -> None:
    args = cli._parser().parse_args(
        ["render", "--run", "run", "--quality", "proxy"]
    )
    assert args.quality == "proxy"
