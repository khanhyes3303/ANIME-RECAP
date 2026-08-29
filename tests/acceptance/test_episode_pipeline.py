from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from anime_review_mvp import cli
from anime_review_mvp.gemini_web import (
    GeminiUltraProfileBinding,
    GeminiUltraSessionReceipt,
    GeminiWebReceipt,
    sha256_file,
)
from anime_review_mvp.jsonio import dump_json, load_json
from anime_review_mvp.models import (
    AtomicBeat,
    AtomicStoryboard,
    AtomicTtsBeat,
    AtomicTtsManifest,
    Claim,
    CriticBeatReview,
    CriticReviewDocument,
    DenseEvidenceDocument,
    DenseFrame,
    Event,
    FrameAnchor,
    FrameAnchorDocument,
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
                148_000,
                "Jiro lao qua cổng.",
                ("shot-0001.jpg",),
                NARRATION_DURATION_MS,
                None,
                "",
                "LOCKED",
                (),
            ),
        ),
    )


def _critic(phase: str) -> CriticReviewDocument:
    source_refs = (
        "beat-001-range-001-start",
        "beat-001-range-001-middle",
        "beat-001-range-001-end",
    )
    evidence_refs = source_refs
    verdict = "NOT_APPLICABLE"
    if phase == "VIDEO":
        evidence_refs += (
            "beat-001-range-001-program-start",
            "beat-001-range-001-program-middle",
            "beat-001-range-001-program-end",
        )
        verdict = "MATCH"
    return CriticReviewDocument(
        phase,
        "producer-acceptance",
        f"critic-{phase.casefold()}",
        (
            CriticBeatReview(
                "beat-001",
                (),
                evidence_refs,
                "Jiro đang chạy qua cổng.",
                "Jiro lao qua cổng.",
                verdict,
                "Đã đối chiếu đủ anchor của beat-001.",
            ),
        ),
    )


def _fake_anchors(
    _video: Path,
    document: object,
    output: Path,
) -> FrameAnchorDocument:
    timeline = "SOURCE" if isinstance(document, AtomicStoryboard) else "PROGRAM"
    program = "-program" if timeline == "PROGRAM" else ""
    anchors = FrameAnchorDocument(
        tuple(
            FrameAnchor(
                f"beat-001-range-001{program}-{position.casefold()}",
                "beat-001",
                "range-001",
                timeline,
                position,
                timestamp,
                str(output / f"{position.casefold()}.jpg"),
            )
            for position, timestamp in zip(
                ("START", "MIDDLE", "END"), (1_000, 211_000, 420_999), strict=True
            )
        )
    )
    output.mkdir(parents=True, exist_ok=True)
    dump_json(output / "anchors.json", anchors)
    return anchors


def _write_web_result(
    run: Path,
    phase: str,
    review: CriticReviewDocument,
    binding: GeminiUltraProfileBinding,
) -> None:
    phase_dir = run / "gemini_web" / phase
    response = phase_dir / f"critic_{phase}.json"
    raw_response = phase_dir / "response.txt"
    screenshot = phase_dir / "screenshots" / "session.png"
    dump_json(response, review)
    raw_response.write_text(response.read_text(encoding="utf-8"), encoding="utf-8")
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"screen")
    request_path = phase_dir / "request.json"
    request = load_json(request_path, object)
    dump_json(
        phase_dir / "receipt.json",
        GeminiWebReceipt(
            run.name,
            phase.upper(),
            request["request_id"],
            sha256_file(request_path),
            str(response),
            sha256_file(response),
            (str(screenshot),),
            GeminiUltraSessionReceipt(
                binding.account_sha256,
                binding.account_hint,
                "Google AI Ultra",
                "Deep Think",
                True,
                "READY",
            ),
            str(raw_response),
            sha256_file(raw_response),
        ),
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
    monkeypatch.setattr(cli, "extract_atomic_source_anchors", _fake_anchors)
    monkeypatch.setattr(cli, "extract_program_anchors", _fake_anchors)

    def fake_dense(
        video: Path,
        storyboard: AtomicStoryboard | None,
        edl: object,
        output_dir: Path,
        timeline: str,
        **_: object,
    ) -> DenseEvidenceDocument:
        del video, storyboard, edl
        frame_path = output_dir / f"beat-001-{timeline.casefold()}-00001000.jpg"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        frame_path.write_bytes(b"frame")
        result = DenseEvidenceDocument(
            timeline,
            (
                DenseFrame(
                    "dense-001", "beat-001", "range-001", timeline, 1_000,
                    str(frame_path), hashlib.sha256(b"frame").hexdigest(),
                ),
            ),
        )
        dump_json(output_dir / "manifest.json", result)
        return result

    def fake_sheets(evidence: DenseEvidenceDocument, output_dir: Path, **_: object) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / f"beat-001-{evidence.timeline.casefold()}-001.jpg").write_bytes(b"sheet")

    monkeypatch.setattr(cli, "extract_dense_beat_evidence", fake_dense)
    monkeypatch.setattr(cli, "build_contact_sheets", fake_sheets)

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
    binding = GeminiUltraProfileBinding("a" * 64, "a***@example.com")
    (tmp_path / ".local").mkdir()
    dump_json(tmp_path / ".local" / "gemini_ultra_profile.json", binding)
    assert cli.main(["web-verify", "prepare", "--run", str(run), "--phase", "script"]) == 0
    _write_web_result(run, "script", _critic("SCRIPT"), binding)
    assert cli.main(["web-verify", "accept", "--run", str(run), "--phase", "script"]) == 0
    assert cli.main(["tts", "--run", str(run)]) == 0
    assert cli.main(["validate", "--run", str(run), "--artifact", "edl"]) == 0
    assert cli.main(["render", "--run", str(run), "--quality", "proxy"]) == 0
    assert cli.main(["web-verify", "prepare", "--run", str(run), "--phase", "proxy"]) == 0
    _write_web_result(run, "proxy", _critic("VIDEO"), binding)
    assert cli.main(["web-verify", "accept", "--run", str(run), "--phase", "proxy"]) == 0
    assert cli.main(["render", "--run", str(run), "--quality", "final"]) == 0
    assert cli.main(["web-verify", "prepare", "--run", str(run), "--phase", "final"]) == 0
    _write_web_result(run, "final", _critic("VIDEO"), binding)
    assert cli.main(["web-verify", "accept", "--run", str(run), "--phase", "final"]) == 0
    assert cli.main(["audit", "--run", str(run), "--phase", "engine"]) == 0

    assert read_state(run).stage is Stage.HOAN_THANH
    assert (episode / "Thanh_pham" / "review_anime.mp4").is_file()
    assert not (episode / "Kich_ban" / "khoa_cau_canh.json").exists()
    assert not (episode / "Bao_cao_Codex").exists()
