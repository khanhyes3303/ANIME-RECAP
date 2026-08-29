from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pytest

from anime_review_mvp import cli
from anime_review_mvp.gemini_web import account_sha256
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.models import (
    AtomicBeat,
    AtomicStoryboard,
    Claim,
    CriticBeatReview,
    CriticReviewDocument,
    DenseEvidenceDocument,
    DenseFrame,
    Event,
    FrameAnchor,
    FrameAnchorDocument,
    Shot,
    ShotDocument,
    SourceRef,
    SpanEdlDocument,
    SpanSourceRange,
    TranscriptDocument,
    TruthDocument,
)
from anime_review_mvp.workflow import Stage, advance, new_state, read_state


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
                    2_700,
                    "Jiro lao vào sân.",
                    ("shot-001.jpg",),
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


def test_cli_validates_storyboard_without_waiting_for_codex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)
    calls: list[Path] = []

    def extract_source(
        source: Path, storyboard: AtomicStoryboard, output: Path
    ) -> FrameAnchorDocument:
        calls.append(source)
        result = FrameAnchorDocument(
            tuple(
                FrameAnchor(
                    f"beat-001-range-001-{position.casefold()}",
                    "beat-001",
                    "range-001",
                    "SOURCE",
                    position,
                    timestamp,
                    str(output / f"{position.casefold()}.jpg"),
                )
                for position, timestamp in zip(
                    ("START", "MIDDLE", "END"), (1_080, 2_500, 3_920), strict=True
                )
            )
        )
        output.mkdir(parents=True, exist_ok=True)
        dump_json(output / "anchors.json", result)
        return result

    monkeypatch.setattr(cli, "extract_atomic_source_anchors", extract_source, raising=False)

    assert cli.main(["validate", "--run", str(run), "--artifact", "storyboard"]) == 0

    assert read_state(run).stage is Stage.VIET_LOI
    assert calls
    assert {metric.stage for metric in read_state(run).stage_metrics} >= {"LAP_STORYBOARD"}
    instruction = json.loads((run / "next_action.json").read_text(encoding="utf-8"))["instruction"]
    assert "Antigravity" in instruction
    assert "Codex" not in instruction


def test_cli_rejects_script_critic_without_all_source_anchors(tmp_path: Path) -> None:
    run, episode = _prepared_storyboard_run(tmp_path)
    advance(run, Stage.LAP_STORYBOARD, Stage.VIET_LOI)
    source_anchors = FrameAnchorDocument(
        tuple(
            FrameAnchor(
                f"beat-001-range-001-{position.casefold()}",
                "beat-001",
                "range-001",
                "SOURCE",
                position,
                timestamp,
                f"{position.casefold()}.jpg",
            )
            for position, timestamp in zip(
                ("START", "MIDDLE", "END"), (1_080, 2_500, 3_920), strict=True
            )
        )
    )
    source_dir = run / "atomic_evidence" / "source"
    source_dir.mkdir(parents=True)
    dump_json(source_dir / "anchors.json", source_anchors)
    dump_json(
        episode / "Bao_cao" / "critic_script.json",
        CriticReviewDocument(
            "SCRIPT",
            "producer-01",
            "critic-script-01",
            (
                CriticBeatReview(
                    "beat-001",
                    (),
                    (source_anchors.anchors[0].anchor_id,),
                    "Jiro chạy qua cổng.",
                    "Jiro chạy.",
                    "NOT_APPLICABLE",
                    "Chỉ mới xem một frame.",
                ),
            ),
        ),
    )

    with pytest.raises(SystemExit):
        cli.main(["validate", "--run", str(run), "--artifact", "critic-script"])


def test_render_parser_accepts_explicit_proxy_quality() -> None:
    args = cli._parser().parse_args(["render", "--run", "run", "--quality", "proxy"])
    assert args.quality == "proxy"


def test_web_verify_parser_requires_action_run_and_phase() -> None:
    args = cli._parser().parse_args(
        ["web-verify", "prepare", "--run", "run", "--phase", "final"]
    )

    assert (args.action, args.phase) == ("prepare", "final")


def test_web_verify_enroll_hashes_email_without_persisting_plaintext(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, episode = _prepared_storyboard_run(tmp_path)
    monkeypatch.setattr(cli.sys, "stdin", StringIO("Ultra@Example.com\n"))

    assert cli.main(
        [
            "web-verify",
            "enroll",
            "--run",
            str(run),
            "--account-hint",
            "ul***@example.com",
        ]
    ) == 0

    binding_path = tmp_path / ".local" / "gemini_ultra_profile.json"
    assert binding_path.is_file()
    payload = json.loads(binding_path.read_text(encoding="utf-8"))
    assert payload["account_sha256"] == account_sha256("Ultra@Example.com")
    assert "Ultra@Example.com" not in binding_path.read_text(encoding="utf-8")


def test_web_verify_prepare_writes_hashed_script_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)
    advance(run, Stage.LAP_STORYBOARD, Stage.VIET_LOI)

    def fake_dense(
        video: Path,
        storyboard: AtomicStoryboard | None,
        edl: SpanEdlDocument | None,
        output_dir: Path,
        timeline: str,
        **_: object,
    ) -> DenseEvidenceDocument:
        frame_path = output_dir / "beat-001-source-00001000.jpg"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        frame_path.write_bytes(b"frame")
        result = DenseEvidenceDocument(
            timeline,
            (
                DenseFrame(
                    "frame-001",
                    "beat-001",
                    "range-001",
                    timeline,
                    1_000,
                    str(frame_path),
                    "a" * 64,
                ),
            ),
        )
        dump_json(output_dir / "manifest.json", result)
        return result

    def fake_sheets(evidence: DenseEvidenceDocument, output_dir: Path, **_: object) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "beat-001-source-001.jpg").write_bytes(b"sheet")

    monkeypatch.setattr(cli, "extract_dense_beat_evidence", fake_dense)
    monkeypatch.setattr(cli, "build_contact_sheets", fake_sheets)

    assert cli.main(
        ["web-verify", "prepare", "--run", str(run), "--phase", "script"]
    ) == 0

    request_path = run / "gemini_web" / "script" / "request.json"
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    assert payload["phase"] == "SCRIPT"
    assert payload["beat_ids"] == ["beat-001"]
    assert payload["evidence_paths"]


def test_web_verify_accept_blocks_script_findings_before_tts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)
    advance(run, Stage.LAP_STORYBOARD, Stage.VIET_LOI)
    advance(run, Stage.VIET_LOI, Stage.CHO_GEMINI_SCRIPT)
    source_anchor = FrameAnchor(
        "beat-001-range-001-start",
        "beat-001",
        "range-001",
        "SOURCE",
        "START",
        1_000,
        "start.jpg",
    )
    source_dir = run / "atomic_evidence" / "source"
    source_dir.mkdir(parents=True)
    dump_json(source_dir / "anchors.json", FrameAnchorDocument((source_anchor,)))
    review = CriticReviewDocument(
        "SCRIPT",
        "producer-01",
        "critic-script-01",
        (
            CriticBeatReview(
                "beat-001",
                ("ACTION_MISMATCH",),
                (source_anchor.anchor_id,),
                "Jiro đứng yên.",
                "Jiro lao vào sân.",
                "NOT_APPLICABLE",
                "Hình không khớp lời.",
            ),
        ),
    )
    monkeypatch.setattr(cli, "_load_verified_critic", lambda *_: review)
    monkeypatch.setattr(cli, "validate_critic_evidence", lambda *_: None)

    assert cli.main(["web-verify", "accept", "--run", str(run), "--phase", "script"]) == 1
    assert read_state(run).stage is Stage.SUA_BEAT
    assert not (Path(read_state(run).episode_dir) / "TTS" / "atomic_tts_manifest.json").exists()


def test_prompt_command_writes_resolved_operator_prompt(tmp_path: Path) -> None:
    root = tmp_path
    run, _ = _prepared_storyboard_run(root)
    brain = root / "Bo_nao_Antigravity"
    brain.mkdir()
    (brain / "PROMPT_MOT_LAN_CHAY.md").write_text(
        "Job: <ĐƯỜNG_DẪN_RUN>\\cong_viec_antigravity.json\nRun: <run_dir>\n",
        encoding="utf-8",
    )
    (run / "cong_viec_antigravity.json").write_text("{}\n", encoding="utf-8")

    assert cli.main(["prompt", "--run", str(run)]) == 0

    output = run / "PROMPT_GUI_ANTIGRAVITY.txt"
    rendered = output.read_text(encoding="utf-8")
    assert str((run / "cong_viec_antigravity.json").resolve()) in rendered
    assert "<ĐƯỜNG_DẪN_RUN>" not in rendered
    assert "<run_dir>" not in rendered
    assert str(run.resolve()) in rendered


def test_prompt_parser_accepts_run_path() -> None:
    args = cli._parser().parse_args(["prompt", "--run", "run"])
    assert args.run == Path("run")


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
