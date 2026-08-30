from __future__ import annotations

import json
from pathlib import Path

import pytest

from anime_review_mvp import cli
from anime_review_mvp.errors import MvpError
from anime_review_mvp.jsonio import dump_json, load_json
from anime_review_mvp.models import (
    Event,
    FrameAnchor,
    FrameAnchorDocument,
    Shot,
    ShotDocument,
    SourceRef,
    SourceRegionAnnotation,
    TranscriptDocument,
    TruthDocument,
)
from anime_review_mvp.render import RenderResult
from anime_review_mvp.situations import (
    EvidenceRange,
    NarrationPlan,
    NarrationUnit,
    SemanticReviewDocument,
    SemanticUnitReview,
    Situation,
    SituationDocument,
    SituationTts,
    SituationTtsManifest,
)
from anime_review_mvp.workflow import Stage, new_state, read_state


def _empty_run(tmp_path: Path) -> Path:
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
    new_state(run, episode_dir=episode, source_video=source)
    return run


def test_parser_exposes_local_situation_artifacts_and_audit() -> None:
    situation = cli._parser().parse_args(
        ["validate", "--run", "run", "--artifact", "situations"]
    )
    narration = cli._parser().parse_args(
        ["validate", "--run", "run", "--artifact", "narration"]
    )
    semantic = cli._parser().parse_args(
        ["validate", "--run", "run", "--artifact", "semantic-review"]
    )
    local_audit = cli._parser().parse_args(["audit", "--run", "run", "--phase", "local"])
    tts = cli._parser().parse_args(
        ["tts", "--run", "run", "--situation", "situation-003"]
    )

    assert (situation.artifact, narration.artifact, semantic.artifact) == (
        "situations",
        "narration",
        "semantic-review",
    )
    assert local_audit.phase == "local"
    assert tts.situation == "situation-003"


def test_gemini_cannot_advance_or_repair_local_run(tmp_path: Path) -> None:
    run, _episode = _local_artifacts(tmp_path)
    before = read_state(run)
    args = cli._parser().parse_args(
        ["gemini-web", "run", "--run", str(run), "--phase", "script"]
    )

    with pytest.raises(MvpError, match="legacy"):
        cli._gemini_web(args)

    assert read_state(run) == before


def test_prepare_missing_tools_writes_clear_next_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _empty_run(tmp_path)

    def missing() -> tuple[Path, ...]:
        raise MvpError("missing required tools: ffmpeg, ffprobe; install them and rerun")

    monkeypatch.setattr(cli, "preflight_media_tools", missing, raising=False)

    with pytest.raises(MvpError, match="ffmpeg, ffprobe"):
        cli._prepare(run)

    payload = json.loads((run / "next_action.json").read_text(encoding="utf-8"))
    assert payload["stage"] == "CHUAN_BI"
    assert payload["code"] == "THIEU_CONG_CU"
    assert "ffmpeg, ffprobe" in payload["instruction"]


def test_prepare_writes_local_situation_editor_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _empty_run(tmp_path)
    monkeypatch.setattr(cli, "preflight_media_tools", lambda: ())
    monkeypatch.setattr(
        cli,
        "probe_source",
        lambda _path: SourceRef("episode.mp4", "a" * 64, 60_000, 320, 180, "1/1000", 1),
    )
    monkeypatch.setattr(
        cli,
        "transcribe_english",
        lambda _source, _cache: TranscriptDocument("en", ()),
    )
    monkeypatch.setattr(
        cli,
        "detect_shots",
        lambda _source, _duration: (Shot("shot-001", 0, 60_000),),
    )

    def frames(_source: Path, _shots: tuple[Shot, ...], output: Path) -> None:
        output.mkdir(parents=True, exist_ok=True)
        (output / "shot-001.jpg").write_bytes(b"jpeg")

    monkeypatch.setattr(cli, "extract_inspection_assets", frames)

    assert cli._prepare(run) == 0

    packet = json.loads((run / "cong_viec_antigravity.json").read_text(encoding="utf-8"))
    assert packet["required_outputs"] == [
        "situation_draft.json", "narration_draft.json"
    ]
    assert "frame_manifest_path" in packet
    assert read_state(run).stage is Stage.CHO_ANTIGRAVITY_TINH_HUONG


def _local_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    run = _empty_run(tmp_path)
    state = read_state(run)
    episode = Path(state.episode_dir)
    new_state(run, stage=Stage.QUAN_SAT, episode_dir=episode, source_video=Path(state.source_video))
    state = read_state(run)
    source = SourceRef(str(state.source_video), "a" * 64, 6_000, 320, 180, "1/1000", 1)
    dump_json(episode / "Dau_vao" / "source_ref.json", source)
    dump_json(
        episode / "Su_that" / "su_that_tap_phim.json",
        TruthDocument(
            (
                Event(
                    "event-001",
                    1_000,
                    5_000,
                    ("Jiro",),
                    "Jiro is attacked and fights back.",
                    "MAIN",
                    1.0,
                ),
            ),
            (
                SourceRegionAnnotation(
                    "region-001", 0, 1_000, "OPENING", "EXCLUDE", "Opening"
                ),
            ),
            True,
        ),
    )
    dump_json(
        run / "shots.json",
        ShotDocument(
            (
                Shot("shot-001", 1_000, 4_000),
                Shot("shot-002", 4_000, 5_000),
            )
        ),
    )
    dump_json(
        episode / "Kich_ban" / "situations.json",
        SituationDocument(
            "LOCAL_EDITOR",
            "situation-v1",
            (
                Situation(
                    "situation-001",
                    1_000,
                    5_000,
                    "MAIN_PLOT",
                    ("Jiro",),
                    "Băng nhóm gây sự.",
                    ("Chúng chủ động tấn công Jiro.",),
                    ("Jiro phản công.",),
                    "Jiro thắng.",
                    ("transcript-001",),
                    ("source-frame-001",),
                    None,
                    None,
                    1.0,
                ),
            ),
        ),
    )
    dump_json(
        episode / "Kich_ban" / "narration_plan.json",
        NarrationPlan(
            "LOCAL_EDITOR",
            "situation-v1",
            (
                NarrationUnit(
                    "unit-001",
                    "situation-001",
                    ("Jiro bị tấn công và phản công.",),
                    "Đám này vừa nhào vô thì Jiro cho ăn hành luôn.",
                    "",
                    "",
                    (
                        EvidenceRange(
                            "range-001",
                            "situation-001",
                            1_000,
                            4_000,
                            ("shot-001",),
                            ("event-001",),
                            ("transcript-001",),
                            ("source-frame-001",),
                            "Jiro phản công.",
                        ),
                    ),
                    "LOCKED",
                ),
            ),
        ),
    )
    return run, episode


def test_local_validation_advances_truth_situations_and_narration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, _episode = _local_artifacts(tmp_path)
    anchor_calls: list[Path] = []
    monkeypatch.setattr(
        cli,
        "extract_situation_anchors",
        lambda _source, _plan, output, **_kwargs: anchor_calls.append(output),
        raising=False,
    )

    assert cli._validate(run, "truth") == 0
    assert read_state(run).stage is Stage.LAP_TINH_HUONG
    assert cli._validate(run, "situations") == 0
    assert read_state(run).stage is Stage.VIET_LOI
    assert cli._validate(run, "narration") == 0
    assert read_state(run).stage is Stage.TAO_TTS
    assert anchor_calls


def test_local_tts_builds_and_validates_adaptive_edl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, episode = _local_artifacts(tmp_path)
    state = read_state(run)
    new_state(
        run,
        stage=Stage.TAO_TTS,
        episode_dir=episode,
        source_video=Path(state.source_video),
    )

    def synthesize(
        _plan: NarrationPlan,
        output_dir: Path,
        _cache_dir: Path,
        **_kwargs: object,
    ) -> SituationTtsManifest:
        manifest = SituationTtsManifest(
            (
                SituationTts(
                    "unit-001",
                    str(output_dir / "unit-001.mp3"),
                    str(output_dir / "unit-001.wav"),
                    2_400,
                    "b" * 64,
                ),
            ),
            str(output_dir / "narration.wav"),
            "fake",
            "voice-001",
            "situation-v1",
            0,
            1,
            2_400,
        )
        dump_json(output_dir / "situation_tts_manifest.json", manifest)
        return manifest

    monkeypatch.setattr(cli, "synthesize_situation_units", synthesize, raising=False)

    assert cli._tts(run, situation_id="situation-001") == 0
    assert read_state(run).stage is Stage.CAN_HINH_VOICE
    assert (episode / "Ke_hoach_canh" / "adaptive_edl.json").is_file()
    assert cli._validate(run, "edl") == 0
    state = read_state(run)
    assert state.stage is Stage.DUNG_PROXY
    assert state.locked_situation_ids == ("situation-001",)


def test_local_render_uses_adaptive_edl_for_proxy_and_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, episode = _local_artifacts(tmp_path)
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    plan = cli.load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
    tts = SituationTtsManifest(
        (
            SituationTts(
                "unit-001",
                str(episode / "TTS" / "unit-001.mp3"),
                str(episode / "TTS" / "unit-001.wav"),
                2_400,
                "b" * 64,
            ),
        ),
        str(episode / "TTS" / "narration.wav"),
        "fake",
        "voice-001",
        "situation-v1",
        0,
        1,
        2_400,
    )
    dump_json(episode / "TTS" / "situation_tts_manifest.json", tts)
    dump_json(
        episode / "Ke_hoach_canh" / "adaptive_edl.json",
        cli.build_adaptive_edl(
            plan,
            tts,
            source_duration_ms=source.duration_ms,
            policy=cli._editorial_policy(episode),
        ),
    )
    state = read_state(run)
    new_state(
        run,
        stage=Stage.DUNG_PROXY,
        episode_dir=episode,
        source_video=Path(state.source_video),
    )
    qualities: list[str] = []

    def render(
        _source: Path,
        _narration: Path,
        _edl: object,
        output: Path,
        *,
        quality: str,
        **_kwargs: object,
    ) -> RenderResult:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"render")
        qualities.append(quality)
        return RenderResult(str(output), 2_400, 2_400, 2_400, 0, 1, 1)

    def anchors(_video: Path, _edl: object, output: Path, **_kwargs: object) -> None:
        dump_json(
            output / "anchors.json",
            FrameAnchorDocument(
                (
                    FrameAnchor(
                        "program-anchor-001",
                        "unit-001",
                        "range-001",
                        "PROGRAM",
                        "MIDDLE",
                        1_200,
                        str(output / "program-anchor-001.jpg"),
                    ),
                )
            ),
        )

    monkeypatch.setattr(cli, "render_review", render)
    monkeypatch.setattr(cli, "extract_adaptive_program_anchors", anchors, raising=False)

    assert cli._render(run, "proxy") == 0
    assert read_state(run).stage is Stage.KIEM_DINH_LOCAL
    new_state(
        run,
        stage=Stage.DUNG_VIDEO_CUOI,
        episode_dir=episode,
        source_video=Path(state.source_video),
    )
    assert cli._render(run, "final") == 0
    assert read_state(run).stage is Stage.KIEM_DINH_ENGINE
    assert qualities == ["proxy", "final"]


def test_local_audit_and_engine_publish_without_gemini(tmp_path: Path) -> None:
    run, episode = _local_artifacts(tmp_path)
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    plan = cli.load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
    tts = SituationTtsManifest(
        (
            SituationTts(
                "unit-001", "unit-001.mp3", "unit-001.wav", 2_400, "b" * 64
            ),
        ),
        "narration.wav",
        "fake",
        "voice-001",
        "situation-v1",
        0,
        1,
        2_400,
    )
    edl = cli.build_adaptive_edl(
        plan,
        tts,
        source_duration_ms=source.duration_ms,
        policy=cli._editorial_policy(episode),
    )
    dump_json(episode / "TTS" / "situation_tts_manifest.json", tts)
    dump_json(episode / "Ke_hoach_canh" / "adaptive_edl.json", edl)
    source_anchors = FrameAnchorDocument(
        (
            FrameAnchor(
                "source-anchor-001",
                "unit-001",
                "range-001",
                "SOURCE",
                "MIDDLE",
                2_500,
                "source.jpg",
            ),
        )
    )
    program_anchors = FrameAnchorDocument(
        (
            FrameAnchor(
                "program-anchor-001",
                "unit-001",
                "range-001",
                "PROGRAM",
                "MIDDLE",
                1_200,
                "program.jpg",
            ),
        )
    )
    dump_json(run / "local_evidence" / "source" / "anchors.json", source_anchors)
    dump_json(run / "local_evidence" / "program" / "anchors.json", program_anchors)
    dump_json(
        episode / "Bao_cao" / "local_semantic_review.json",
        SemanticReviewDocument(
            "LOCAL_SEMANTIC_AUDITOR",
            (
                SemanticUnitReview(
                    "unit-001",
                    True,
                    (),
                    ("transcript-001",),
                    ("source-anchor-001",),
                    ("program-anchor-001",),
                    "Khớp.",
                ),
            ),
        ),
    )
    render = RenderResult("proxy.mp4", 2_400, 2_400, 2_400, 0, 1, 1)
    dump_json(run / "proxy" / "render_result.json", render)
    state = read_state(run)
    new_state(
        run,
        stage=Stage.KIEM_DINH_LOCAL,
        episode_dir=episode,
        source_video=Path(state.source_video),
    )

    assert cli._validate(run, "semantic-review") == 0
    assert read_state(run).stage is Stage.KIEM_DINH_LOCAL
    assert cli._audit(run, "local", None) == 0
    assert read_state(run).stage is Stage.DUNG_VIDEO_CUOI

    final = run / "final_candidate.mp4"
    final.write_bytes(b"final")
    dump_json(run / "final_render_result.json", render)
    dump_json(
        run / "local_evidence" / "program_final" / "anchors.json", program_anchors
    )
    new_state(
        run,
        stage=Stage.KIEM_DINH_ENGINE,
        episode_dir=episode,
        source_video=Path(state.source_video),
    )

    assert cli._audit(run, "engine", None) == 0
    assert read_state(run).stage is Stage.HOAN_THANH
    assert (episode / "Thanh_pham" / "review_anime.mp4").read_bytes() == b"final"
