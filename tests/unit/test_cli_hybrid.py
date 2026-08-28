from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp import cli
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.models import (
    Claim,
    CodexSemanticReview,
    Event,
    FrameAnchor,
    FrameAnchorDocument,
    NarrationSpan,
    NarrationSpanDocument,
    SourceRef,
    SpanSemanticReview,
    SpanSourceRange,
    SpanTts,
    SpanTtsManifest,
    TruthDocument,
)
from anime_review_mvp.render import RenderResult
from anime_review_mvp.workflow import Stage, new_state, read_state


def _locked(duration_ms: int) -> NarrationSpanDocument:
    return NarrationSpanDocument(
        spans=(
            NarrationSpan(
                "span-001",
                "Jiro lao qua cổng.",
                ("claim-001",),
                ("event-001",),
                ("Jiro",),
                "Jiro chạy qua cổng.",
                (
                    SpanSourceRange(
                        "range-001", 0, duration_ms, "scene-001", "beat-001",
                        ("shot-001",), ("event-001",),
                    ),
                ),
            ),
        ),
        claims=(Claim("claim-001", "ACTION", "Jiro runs.", ("event-001",)),),
        owner="CODEX",
    )


def _anchors(timeline: str, output_dir: Path) -> FrameAnchorDocument:
    output_dir.mkdir(parents=True, exist_ok=True)
    items = tuple(
        FrameAnchor(
            f"span-001-{timeline.lower()}-{position.lower()}",
            "span-001",
            "range-001",
            timeline,
            position,
            timestamp,
            str(output_dir / f"{position.lower()}.jpg"),
        )
        for position, timestamp in (("START", 80), ("MIDDLE", 500), ("END", 920))
    )
    document = FrameAnchorDocument(items)
    dump_json(output_dir / "anchors.json", document)
    return document


def _episode(tmp_path: Path, duration_ms: int) -> tuple[Path, Path, Path]:
    episode = tmp_path / "Kho_Anime" / "A" / "Mua_01" / "Tap_001"
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    directories = (
        "Dau_vao", "Su_that", "Kich_ban", "TTS", "Ke_hoach_canh",
        "Thanh_pham", "Bao_cao",
    )
    for directory in directories:
        (episode / directory).mkdir(parents=True, exist_ok=True)
    dump_json(
        episode / "Dau_vao" / "source_ref.json",
        SourceRef(str(source), "a" * 64, duration_ms, 320, 180, "1/1000", 1),
    )
    dump_json(
        episode / "Su_that" / "su_that_tap_phim.json",
        TruthDocument(
            (Event("event-001", 0, duration_ms, ("Jiro",), "Jiro runs.", "MAIN", 1.0),),
            (),
            True,
        ),
    )
    dump_json(episode / "Kich_ban" / "khoa_cau_canh.json", _locked(duration_ms))
    run = tmp_path / "Tam_dang_xu_ly" / "run"
    return episode, source, run


def test_lock_validates_codex_spans_and_creates_source_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    episode, source, run = _episode(tmp_path, 1_000)
    new_state(run, stage=Stage.CODEX_BIEN_TAP, episode_dir=episode, source_video=source)

    def fake_extract(
        video: Path, document: NarrationSpanDocument, output_dir: Path, **_: object
    ) -> FrameAnchorDocument:
        assert video == source.resolve()
        assert document.owner == "CODEX"
        return _anchors("SOURCE", output_dir)

    monkeypatch.setattr(cli, "extract_span_anchors", fake_extract)

    assert cli.main(["lock", "--run", str(run)]) == 0
    assert read_state(run).stage is Stage.TAO_TTS
    assert (run / "codex_evidence" / "source" / "anchors.json").is_file()


def test_tts_builds_locked_edl_then_render_keeps_old_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    episode, source, run = _episode(tmp_path, 1_000)
    new_state(run, stage=Stage.TAO_TTS, episode_dir=episode, source_video=source)
    old_final = episode / "Thanh_pham" / "review_anime.mp4"
    old_final.write_bytes(b"old")

    def fake_tts(
        document: NarrationSpanDocument, output_dir: Path, **_: object
    ) -> SpanTtsManifest:
        assert document.owner == "CODEX"
        narration = output_dir / "narration.wav"
        narration.write_bytes(b"voice")
        manifest = SpanTtsManifest(
            (SpanTts("span-001", "1.mp3", "1.wav", 1_000),),
            str(narration), "fake", "BV074_streaming",
        )
        dump_json(output_dir / "span_tts_manifest.json", manifest)
        return manifest

    def fake_render(
        source_path: Path, narration: Path, edl: object, output: Path, **_: object
    ) -> RenderResult:
        del source_path, narration, edl
        output.write_bytes(b"candidate")
        return RenderResult(str(output), 1_000, 1_000, 1_000, 0, 1, 1)

    def fake_program(
        video: Path, edl: object, output_dir: Path, **_: object
    ) -> FrameAnchorDocument:
        del video, edl
        return _anchors("PROGRAM", output_dir)

    monkeypatch.setattr(cli, "synthesize_spans", fake_tts)
    monkeypatch.setattr(cli, "render_review", fake_render)
    monkeypatch.setattr(cli, "extract_program_anchors", fake_program)

    assert cli.main(["tts", "--run", str(run)]) == 0
    assert cli.main(["validate", "--run", str(run), "--artifact", "edl"]) == 0
    assert cli.main(["render", "--run", str(run)]) == 0
    assert old_final.read_bytes() == b"old"
    assert (run / "review_candidate.mp4").read_bytes() == b"candidate"
    assert read_state(run).stage is Stage.KIEM_DINH_VIDEO


def test_engine_audit_publishes_candidate_and_backs_up_old_final(tmp_path: Path) -> None:
    episode, source, run = _episode(tmp_path, 420_000)
    new_state(run, stage=Stage.KIEM_DINH_VIDEO, episode_dir=episode, source_video=source)
    candidate = run / "review_candidate.mp4"
    candidate.write_bytes(b"new")
    final = episode / "Thanh_pham" / "review_anime.mp4"
    final.write_bytes(b"old")
    dump_json(
        episode / "TTS" / "span_tts_manifest.json",
        SpanTtsManifest(
            (SpanTts("span-001", "1.mp3", "1.wav", 420_000),),
            "narration.wav", "fake", "BV074_streaming",
        ),
    )
    source_anchors = _anchors("SOURCE", run / "codex_evidence" / "source")
    program_anchors = _anchors("PROGRAM", run / "codex_evidence" / "program")
    dump_json(
        run / "render_result.json",
        RenderResult(str(candidate), 420_000, 420_000, 420_000, 0, 1, 1),
    )
    evidence = tuple(
        item.anchor_id for item in (*source_anchors.anchors, *program_anchors.anchors)
    )
    review_path = episode / "Bao_cao_Codex" / "codex_semantic_review.json"
    dump_json(
        review_path,
        CodexSemanticReview(
            "CODEX",
            (SpanSemanticReview("span-001", True, (), evidence, "Khớp hình và lời."),),
        ),
    )

    assert cli.main(
        ["audit", "--run", str(run), "--phase", "video", "--codex-review", str(review_path)]
    ) == 0
    assert read_state(run).stage is Stage.HOAN_THANH
    assert final.read_bytes() == b"new"
    backups = list((episode / "Bao_cao" / "phien_ban_cu").glob("*.mp4"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b"old"
    assert (episode / "Bao_cao" / "kiem_dinh_engine.json").is_file()
