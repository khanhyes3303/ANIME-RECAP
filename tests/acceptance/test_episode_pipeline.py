from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp import cli
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.models import (
    AtomicBeat,
    AtomicStoryboard,
    AtomicTtsBeat,
    AtomicTtsManifest,
    Claim,
    CriticBeatReview,
    CriticReviewDocument,
    Event,
    SceneBeat,
    ScenePacket,
    ScenePacketDocument,
    SceneShot,
    Shot,
    SourceRef,
    SpanSourceRange,
    TranscriptDocument,
    TruthDocument,
    TtsCacheStats,
)
from anime_review_mvp.render import RenderResult
from anime_review_mvp.workflow import Stage, read_state

SOURCE_DURATION_MS = 421_000
NARRATION_DURATION_MS = 420_000


def _storyboard() -> AtomicStoryboard:
    return AtomicStoryboard(
        "ANTIGRAVITY",
        "atomic-v1",
        "producer-acceptance",
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
                        421_000,
                        "scene-001",
                        "beat-001",
                        ("shot-0001",),
                        ("event-001",),
                    ),
                ),
                "Jiro chạy qua cổng.",
                ("Jiro",),
                ("Jiro",),
                "ACTION",
                1_000,
                2_000,
                "Jiro lao qua cổng.",
                ("frame-1000.jpg",),
                NARRATION_DURATION_MS,
                None,
                "",
                "LOCKED",
                (),
            ),
        ),
    )


def _critic(phase: str) -> CriticReviewDocument:
    return CriticReviewDocument(
        phase,
        "producer-acceptance",
        f"critic-{phase.casefold()}",
        (CriticBeatReview("beat-001", (), ("frame-1000.jpg",), "Khớp hình và lời."),),
    )


def test_one_antigravity_run_reaches_final_without_codex_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"source")

    monkeypatch.setattr(
        cli,
        "probe_source",
        lambda path: SourceRef(str(path), "a" * 64, SOURCE_DURATION_MS, 320, 180, "1/1000", 1),
    )
    monkeypatch.setattr(
        cli,
        "transcribe_english",
        lambda video, output: TranscriptDocument("en", ()),
    )
    monkeypatch.setattr(
        cli,
        "detect_shots",
        lambda video, duration: (Shot("shot-0001", 0, duration),),
    )
    monkeypatch.setattr(cli, "extract_inspection_assets", lambda *args, **kwargs: ())

    def fake_tts(storyboard: AtomicStoryboard, output: Path, cache: Path) -> AtomicTtsManifest:
        del cache
        output.mkdir(parents=True, exist_ok=True)
        narration = output / "narration.wav"
        narration.write_bytes(b"voice")
        manifest = AtomicTtsManifest(
            (
                AtomicTtsBeat(
                    "beat-001",
                    str(output / "beat-001.mp3"),
                    str(output / "beat-001.wav"),
                    NARRATION_DURATION_MS,
                    "cache-key",
                ),
            ),
            str(narration),
            "fake",
            "BV074_streaming",
            storyboard.policy_version,
            TtsCacheStats(0, 1),
        )
        dump_json(output / "atomic_tts_manifest.json", manifest)
        return manifest

    def fake_render(
        source_path: Path,
        narration: Path,
        edl: object,
        output: Path,
        **_: object,
    ) -> RenderResult:
        del source_path, narration, edl
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"video")
        return RenderResult(
            str(output),
            NARRATION_DURATION_MS,
            NARRATION_DURATION_MS,
            NARRATION_DURATION_MS,
            0,
            1,
            1,
        )

    monkeypatch.setattr(cli, "synthesize_atomic_beats", fake_tts)
    monkeypatch.setattr(cli, "render_review", fake_render)
    monkeypatch.setattr(cli, "extract_program_anchors", lambda *args, **kwargs: None)

    assert (
        cli.main(
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
        )
        == 0
    )
    run = next((tmp_path / "Tam_dang_xu_ly").iterdir())
    episode = Path(read_state(run).episode_dir)
    assert cli.main(["prepare", "--run", str(run)]) == 0

    truth = TruthDocument(
        (Event("event-001", 1_000, 421_000, ("Jiro",), "Jiro runs.", "MAIN", 1.0),),
        (),
        True,
    )
    packet = ScenePacketDocument(
        (
            ScenePacket(
                "scene-001",
                1_000,
                421_000,
                "Jiro chạy.",
                ("event-001",),
                (
                    SceneShot(
                        "shot-0001", 1_000, 421_000, "MUST_KEEP", ("event-001",), "Hành động chính."
                    ),
                ),
                (
                    SceneBeat(
                        "beat-001", 1_000, 421_000, ("event-001",), ("shot-0001",), ("beat-001",)
                    ),
                ),
                ("beat-001",),
            ),
        ),
    )
    dump_json(episode / "Su_that" / "su_that_tap_phim.json", truth)
    dump_json(episode / "Su_that" / "scene_packets.json", packet)
    assert cli.main(["validate", "--run", str(run), "--artifact", "truth"]) == 0
    assert cli.main(["validate", "--run", str(run), "--artifact", "scene"]) == 0

    dump_json(episode / "Kich_ban" / "atomic_storyboard.json", _storyboard())
    assert cli.main(["validate", "--run", str(run), "--artifact", "storyboard"]) == 0
    dump_json(episode / "Bao_cao" / "critic_script.json", _critic("SCRIPT"))
    assert cli.main(["validate", "--run", str(run), "--artifact", "critic-script"]) == 0
    assert cli.main(["tts", "--run", str(run)]) == 0
    assert cli.main(["validate", "--run", str(run), "--artifact", "edl"]) == 0
    assert cli.main(["render", "--run", str(run), "--quality", "proxy"]) == 0
    dump_json(episode / "Bao_cao" / "critic_video.json", _critic("VIDEO"))
    assert cli.main(["validate", "--run", str(run), "--artifact", "critic-video"]) == 0
    assert cli.main(["render", "--run", str(run), "--quality", "final"]) == 0
    assert cli.main(["audit", "--run", str(run), "--phase", "engine"]) == 0

    assert read_state(run).stage is Stage.HOAN_THANH
    assert (episode / "Thanh_pham" / "review_anime.mp4").is_file()
    assert not (episode / "Kich_ban" / "khoa_cau_canh.json").exists()
    assert not (episode / "Bao_cao_Codex").exists()
