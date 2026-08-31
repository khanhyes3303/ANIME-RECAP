from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from anime_review_mvp import cli, gemini_session
from anime_review_mvp.editor_provenance import create_editor_task
from anime_review_mvp.errors import MvpError
from anime_review_mvp.gemini_session import GeminiSessionMetadata, GeminiSessionRegistry
from anime_review_mvp.gemini_web import account_sha256
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.models import (
    AtomicBeat,
    AtomicStoryboard,
    Claim,
    CriticBeatReview,
    CriticReviewDocument,
    Event,
    FrameAnchor,
    FrameAnchorDocument,
    Shot,
    ShotDocument,
    SourceRef,
    SpanSourceRange,
    TranscriptDocument,
    TruthDocument,
)
from anime_review_mvp.workflow import (
    Stage,
    advance,
    begin_proxy_verifier_task,
    new_state,
    read_state,
)
from anime_review_mvp.render import RenderResult
from anime_review_mvp.run_identity import RunCodeIdentity


def test_cli_rejects_run_created_by_another_checkout(tmp_path: Path) -> None:
    episode = tmp_path / "Kho_Anime" / "A" / "Mua_01" / "Tap_001"
    episode.mkdir(parents=True)
    run = tmp_path / "Tam_dang_xu_ly" / "run"
    new_state(run, episode_dir=episode)
    state_path = run / "run_state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["repository_root"] = str((tmp_path / "different-checkout").resolve())
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(MvpError, match="RUN_CODE_IDENTITY_MISMATCH"):
        cli._episode(run)


def test_autonomous_prompt_uses_absolute_engine_entrypoint(tmp_path: Path) -> None:
    rendered = cli._autonomous_task_prompt(
        "Làm job hiện tại.",
        tmp_path / "run",
        "accept-antigravity --task task-001",
    )
    entrypoint = Path(cli.__file__).resolve().parents[2] / "run_episode.py"

    project = entrypoint.parent
    assert f'uv run --project "{project}" python "{entrypoint}" accept-antigravity' in rendered
    assert f'uv run --project "{project}" python "{entrypoint}" operator' in rendered


def test_main_rejects_proxy_approval_from_another_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    episode = tmp_path / "Kho_Anime" / "A" / "Mua_01" / "Tap_001"
    episode.mkdir(parents=True)
    run = tmp_path / "run"
    new_state(run, stage=Stage.CHO_NGUOI_DUNG_DUYET_PROXY, episode_dir=episode)
    state_path = run / "run_state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["repository_root"] = str((tmp_path / "other-checkout").resolve())
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    called: list[Path] = []
    monkeypatch.setattr(cli, "_approve_proxy_command", lambda path: called.append(path) or 0)

    with pytest.raises(SystemExit) as exc:
        cli.main(["approve-proxy", "--run", str(run)])

    assert exc.value.code == 2
    assert called == []


def test_legacy_run_identity_is_persisted_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "run"
    new_state(run)
    state_path = run / "run_state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    for field in ("repository_root", "code_commit", "contract_version"):
        payload.pop(field)
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    identity = RunCodeIdentity(str(tmp_path.resolve()), "c" * 40)
    monkeypatch.setattr(cli, "capture_run_code_identity", lambda _path: identity)
    monkeypatch.setattr(cli, "validate_run_code_identity", lambda *_args: None)

    cli._validate_run_command_identity(run)

    persisted = read_state(run)
    assert persisted.repository_root == identity.repository_root
    assert persisted.code_commit == identity.git_commit
    assert persisted.contract_version == identity.contract_version


def test_proxy_verifier_cannot_override_failed_machine_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    episode = tmp_path / "Kho_Anime" / "A" / "Mua_01" / "Tap_001"
    episode.mkdir(parents=True)
    run = tmp_path / "Tam_dang_xu_ly" / "run"
    new_state(
        run,
        stage=Stage.CHO_ANTIGRAVITY_KIEM_DINH_PROXY,
        episode_dir=episode,
    )
    machine_input = run / "proxy" / "render_result.json"
    machine_input.parent.mkdir(parents=True)
    machine_input.write_text("{}", encoding="utf-8")
    task = create_editor_task(
        run,
        run.name,
        "__episode__",
        1,
        (machine_input,),
        task_kind="PROXY_AUDIT",
        task_id="__episode__-revision-001",
        allowed_outputs=("proxy_audit_draft.json",),
        expected_stage="ANTIGRAVITY_VERIFIER",
    )
    begin_proxy_verifier_task(run, task.task_id, task.revision)

    def reject_machine_audit(_run: Path, _episode: Path) -> object:
        raise MvpError("PROXY_MACHINE_AUDIT_REQUIRED: PRODUCTION_DURATION_OUT_OF_RANGE")

    monkeypatch.setattr(cli, "require_current_proxy_machine_pass", reject_machine_audit)

    with pytest.raises(MvpError, match="PROXY_MACHINE_AUDIT_REQUIRED"):
        cli._accept_verifier_command(run, task.task_id, run / "staging")

    assert read_state(run).stage is Stage.CHO_ANTIGRAVITY_KIEM_DINH_PROXY


def test_machine_audit_rejects_proxy_changed_after_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "run"
    proxy = run / "proxy" / "review_proxy.mp4"
    proxy.parent.mkdir(parents=True)
    proxy.write_bytes(b"changed proxy")
    dump_json(
        run / "proxy" / "render_result.json",
        RenderResult(str(proxy.resolve()), 420_000, 420_000, 420_000, 0, 1, 1, "a" * 64),
    )
    monkeypatch.setattr(
        cli,
        "probe_render",
        lambda _path: RenderResult(
            str(proxy.resolve()), 420_000, 420_000, 420_000, 0, 1, 1, "b" * 64
        ),
    )

    with pytest.raises(MvpError, match="PROXY_RENDER_ARTIFACT_MISMATCH"):
        cli._verified_current_proxy_render(run)


def test_next_action_exposes_simple_public_stage(tmp_path: Path) -> None:
    run = tmp_path / "run"
    new_state(run, stage=Stage.TAO_TTS_TINH_HUONG)

    cli._write_next(run, "Tạo voice rồi khớp cảnh.")

    payload = json.loads((run / "next_action.json").read_text(encoding="utf-8"))
    assert payload["stage"] == "TAO_TTS_TINH_HUONG"
    assert payload["public_stage"] == "TAO_VOICE_VA_KHOP_CANH"


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


def test_gemini_web_parser_requires_action_run_and_phase() -> None:
    args = cli._parser().parse_args(
        ["gemini-web", "run", "--run", "run", "--phase", "final"]
    )

    assert (args.action, args.phase) == ("run", "final")


def test_gemini_web_parser_accepts_continue_and_stop() -> None:
    continue_args = cli._parser().parse_args(
        [
            "gemini-web",
            "continue",
            "--run",
            "run",
            "--phase",
            "script",
            "--prompt-file",
            "feedback.txt",
        ]
    )
    stop_args = cli._parser().parse_args(["gemini-web", "stop", "--run", "run"])

    assert (continue_args.action, continue_args.prompt_file.name) == (
        "continue",
        "feedback.txt",
    )
    assert stop_args.action == "stop"


def test_gemini_web_parser_accepts_explicit_new_chat() -> None:
    args = cli._parser().parse_args(
        ["gemini-web", "new-chat", "--run", "run", "--phase", "proxy"]
    )

    assert (args.action, args.phase) == ("new-chat", "proxy")


def test_gemini_web_parser_accepts_show() -> None:
    args = cli._parser().parse_args(["gemini-web", "show", "--run", "run"])

    assert args.action == "show"


def test_gemini_web_continue_rejects_prompt_outside_run(tmp_path: Path) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)
    prompt = tmp_path / "outside-feedback.txt"
    prompt.write_text("repair", encoding="utf-8")

    with pytest.raises(MvpError, match="outside"):
        cli._gemini_web_continue(run, "script", prompt)


def test_gemini_web_stop_without_session_is_noop(tmp_path: Path) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)

    assert cli._gemini_web_stop(run) == 0


def test_gemini_web_show_restores_registered_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)
    registry = GeminiSessionRegistry(tmp_path / ".local" / "gemini_operator_session.json")
    registry.save(
        GeminiSessionMetadata(
            run.name,
            123,
            "127.0.0.1:9222",
            None,
            "2026-08-30T12:00:00+00:00",
            {},
        )
    )

    class Page:
        def __init__(self) -> None:
            self.shown = False

        def show(self) -> None:
            self.shown = True

    class Launch:
        def __init__(self) -> None:
            self.page = Page()
            self.detached = False

        def detach(self) -> None:
            self.detached = True

    launch = Launch()
    events: list[str] = []
    monkeypatch.setattr(gemini_session, "_pid_is_alive", lambda _pid: True)
    monkeypatch.setattr(gemini_session, "_debugger_is_alive", lambda _address: True)
    monkeypatch.setattr(
        cli,
        "ensure_managed_chrome_visible",
        lambda _root, _metadata: events.append("native-visible") or 9001,
    )
    monkeypatch.setattr(
        cli,
        "connect_managed_chrome",
        lambda _metadata: events.append("selenium-connect") or launch,
    )

    assert cli._gemini_web_show(run) == 0
    assert events == ["native-visible", "selenium-connect"]
    assert launch.page.shown is True
    assert launch.detached is True


def test_gemini_web_show_starts_visible_operator_when_session_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)

    class Page:
        def __init__(self) -> None:
            self.shown = False

        def show(self) -> None:
            self.shown = True

    class Launch:
        chrome_pid = 456
        debugger_address = "127.0.0.1:9333"

        def __init__(self) -> None:
            self.page = Page()
            self.detached = False

        def detach(self) -> None:
            self.detached = True

    launch = Launch()
    monkeypatch.setattr(cli, "launch_managed_chrome", lambda _root: launch)

    assert cli._gemini_web_show(run) == 0

    metadata = GeminiSessionRegistry(
        tmp_path / ".local" / "gemini_operator_session.json"
    ).load()
    assert metadata is not None
    assert metadata.run_id == run.name
    assert metadata.chrome_pid == 456
    assert launch.page.shown is True
    assert launch.detached is True


def test_final_gemini_web_pass_cleans_registered_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)
    new_state(run, stage=Stage.CHO_GEMINI_FINAL)
    calls: list[Path] = []
    monkeypatch.setattr(cli, "run_operator_phase", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli, "_accept_operator_review", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(cli, "_gemini_web_stop", lambda path: calls.append(path) or 0)

    assert cli._gemini_web_run(run, "final") == 0
    assert calls == [run]


def test_gemini_web_stop_closes_process_and_clears_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)
    registry = GeminiSessionRegistry(tmp_path / ".local" / "gemini_operator_session.json")
    registry.save(
        GeminiSessionMetadata(
            run.name,
            123,
            "127.0.0.1:9222",
            "https://gemini.google.com/app/chat-123",
            "2026-08-30T12:00:00+00:00",
            {},
        )
    )

    class Launch:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    launch = Launch()
    monkeypatch.setattr(cli, "connect_managed_chrome", lambda _metadata: launch)

    assert cli._gemini_web_stop(run) == 0
    assert launch.closed is True
    assert not registry.path.exists()


def test_gemini_web_enroll_hashes_email_without_persisting_plaintext(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, episode = _prepared_storyboard_run(tmp_path)
    monkeypatch.setattr(cli.sys, "stdin", StringIO("Ultra@Example.com\n"))

    assert cli.main(
        [
            "gemini-web",
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


def test_gemini_web_prepare_no_longer_exists() -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            ["gemini-web", "prepare", "--run", "run", "--phase", "script"]
        )


def test_operator_acceptance_blocks_script_findings_before_tts(
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
    monkeypatch.setattr(cli, "validate_critic_evidence", lambda *_: None)

    assert cli._accept_operator_review(run, "script", review) == 1
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


def test_prompt_command_bootstraps_fresh_run_before_first_job(tmp_path: Path) -> None:
    episode = tmp_path / "Kho_Anime" / "A" / "Mua_01" / "Tap_001"
    episode.mkdir(parents=True)
    source = tmp_path / "episode.mp4"
    source.write_bytes(b"source")
    run = tmp_path / "Tam_dang_xu_ly" / "fresh-run"
    new_state(run, stage=Stage.CHUAN_BI, episode_dir=episode, source_video=source)
    brain = tmp_path / "Bo_nao_Antigravity"
    brain.mkdir()
    (brain / "PROMPT_MOT_LAN_CHAY.md").write_text(
        "Job: <ĐƯỜNG_DẪN_RUN>\\cong_viec_antigravity.json\n"
        "Run: <run_dir>\n",
        encoding="utf-8",
    )

    assert cli.main(["prompt", "--run", str(run)]) == 0

    rendered = (run / "PROMPT_GUI_ANTIGRAVITY.txt").read_text(encoding="utf-8")
    assert f'operator --run "{run.resolve()}"' in rendered
    assert str((run / "cong_viec_antigravity.json").resolve()) in rendered


def test_prompt_command_preserves_task_specific_prompt(tmp_path: Path) -> None:
    root = tmp_path
    run, _ = _prepared_storyboard_run(root)
    brain = root / "Bo_nao_Antigravity"
    brain.mkdir()
    (brain / "PROMPT_MOT_LAN_CHAY.md").write_text(
        "STALE TEMPLATE <ĐƯỜNG_DẪN_RUN>\\cong_viec_antigravity.json\n",
        encoding="utf-8",
    )
    (run / "cong_viec_antigravity.json").write_text(
        '{"task_kind":"STRUCTURE","required_outputs":["situation_index_draft.json"]}\n',
        encoding="utf-8",
    )
    output = run / "PROMPT_GUI_ANTIGRAVITY.txt"
    exact_prompt = "EXACT STRUCTURE PROMPT: situation_index_draft.json\n"
    output.write_text(exact_prompt, encoding="utf-8")

    assert cli.main(["prompt", "--run", str(run)]) == 0

    assert output.read_text(encoding="utf-8") == exact_prompt


def test_prompt_parser_accepts_run_path() -> None:
    args = cli._parser().parse_args(["prompt", "--run", "run"])
    assert args.run == Path("run")


def test_manual_web_accept_no_longer_exists() -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(
            ["web-verify", "accept", "--run", "run", "--phase", "script"]
        )


def test_gemini_web_browser_failure_stops_run_for_human(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from anime_review_mvp.gemini_selenium import GeminiBrowserError

    run = tmp_path / "Tam_dang_xu_ly" / "run-01"
    new_state(run, stage=Stage.VIET_LOI)

    def fail(*_: object, **__: object) -> object:
        raise GeminiBrowserError("LOGIN_REQUIRED", "login")

    monkeypatch.setattr(cli, "run_operator_phase", fail)

    assert cli.main(
        ["gemini-web", "run", "--run", str(run), "--phase", "script"]
    ) == 1
    assert read_state(run).stage is Stage.CAN_CON_NGUOI_XU_LY
    next_action = json.loads((run / "next_action.json").read_text(encoding="utf-8"))
    assert next_action["code"] == "CAN_DANG_NHAP_GEMINI_ULTRA"
    assert "gemini-web show" in next_action["instruction"]


def test_gemini_web_run_resumes_human_browser_stop_with_full_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-01"
    new_state(run, stage=Stage.CAN_CON_NGUOI_XU_LY)
    phases: list[str] = []

    def run_phase(run_dir: Path, phase: str) -> object:
        assert run_dir == run
        phases.append(phase)
        return object()

    monkeypatch.setattr(cli, "run_operator_phase", run_phase)
    monkeypatch.setattr(cli, "_accept_operator_review", lambda *_args: 0)

    assert cli._gemini_web_run(run, "script") == 0
    assert phases == ["SCRIPT"]
    assert read_state(run).stage is Stage.CHO_GEMINI_SCRIPT


def test_gemini_web_new_chat_forces_full_packet_in_fresh_conversation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-01"
    new_state(run, stage=Stage.CAN_CON_NGUOI_XU_LY)
    calls: list[tuple[str, bool]] = []

    def run_phase(
        run_dir: Path,
        phase: str,
        *,
        force_new_chat: bool = False,
    ) -> object:
        assert run_dir == run
        calls.append((phase, force_new_chat))
        return object()

    monkeypatch.setattr(cli, "run_operator_phase", run_phase)
    monkeypatch.setattr(cli, "_accept_operator_review", lambda *_args: 0)

    assert cli._gemini_web_run(run, "proxy", force_new_chat=True) == 0
    assert calls == [("PROXY", True)]


def test_gemini_web_run_repairs_invalid_critic_in_same_chat_without_reupload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-01"
    new_state(run, stage=Stage.PHAN_BIEN_VIDEO)
    repair_prompt = run / "gemini_web" / "proxy" / "auto_repair_prompt_02.txt"
    repair_prompt.parent.mkdir(parents=True)
    repair_prompt.write_text("repair anchors without changing verdicts", encoding="utf-8")
    calls: list[Path | None] = []
    validations = 0
    accepted: list[object] = []

    def run_phase(
        run_dir: Path,
        phase: str,
        *,
        prompt_override: Path | None = None,
        force_new_chat: bool = False,
    ) -> object:
        assert run_dir == run
        assert phase == "PROXY"
        assert force_new_chat is False
        calls.append(prompt_override)
        return object()

    def validate_review(run_dir: Path, phase: str, review: object) -> None:
        nonlocal validations
        assert run_dir == run
        assert phase == "PROXY"
        validations += 1
        if validations == 1:
            raise MvpError("critic review lacks engine SOURCE and PROGRAM anchors")

    monkeypatch.setattr(cli, "run_operator_phase", run_phase)
    monkeypatch.setattr(cli, "_validate_operator_review", validate_review, raising=False)
    monkeypatch.setattr(
        cli,
        "_write_critic_repair_prompt",
        lambda *_args, **_kwargs: repair_prompt,
        raising=False,
    )
    monkeypatch.setattr(
        cli,
        "_accept_operator_review",
        lambda _run, _phase, review: accepted.append(review) or 0,
    )

    assert cli._gemini_web_run(run, "proxy") == 0
    assert calls == [None, repair_prompt]
    assert validations == 2
    assert len(accepted) == 1
    assert read_state(run).stage is Stage.CHO_GEMINI_PROXY


def test_critic_repair_prompt_requires_all_engine_anchors_without_forcing_match(
    tmp_path: Path,
) -> None:
    run, _ = _prepared_storyboard_run(tmp_path)
    source_anchors = FrameAnchorDocument(
        tuple(
            FrameAnchor(
                f"beat-001-range-001-{position.casefold()}",
                "beat-001",
                "range-001",
                "SOURCE",
                position,
                timestamp,
                f"source-{position.casefold()}.jpg",
            )
            for position, timestamp in (
                ("START", 1_000),
                ("MIDDLE", 2_500),
                ("END", 4_000),
            )
        )
    )
    program_anchors = FrameAnchorDocument(
        tuple(
            FrameAnchor(
                f"beat-001-range-001-program-{position.casefold()}",
                "beat-001",
                "range-001",
                "PROGRAM",
                position,
                timestamp,
                f"program-{position.casefold()}.jpg",
            )
            for position, timestamp in (
                ("START", 0),
                ("MIDDLE", 1_500),
                ("END", 3_000),
            )
        )
    )
    dump_json(run / "atomic_evidence" / "source" / "anchors.json", source_anchors)
    dump_json(run / "atomic_evidence" / "program" / "anchors.json", program_anchors)

    prompt_path = cli._write_critic_repair_prompt(
        run,
        "PROXY",
        MvpError("critic review lacks engine SOURCE and PROGRAM anchors"),
        turn_number=2,
    )
    prompt = prompt_path.read_text(encoding="utf-8")

    for anchor in (*source_anchors.anchors, *program_anchors.anchors):
        assert anchor.anchor_id in prompt
    assert "giữ nguyên các finding_codes và sync_verdict" in prompt
    assert "không được đổi lỗi thật thành MATCH" in prompt
    assert '"finding_codes": []' not in prompt
    assert '"sync_verdict": "MATCH"' not in prompt


def test_gemini_web_run_repairs_invalid_json_response_in_same_chat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-01"
    new_state(run, stage=Stage.VIET_LOI)
    repair_prompt = run / "gemini_web" / "script" / "auto_repair_prompt_02.txt"
    repair_prompt.parent.mkdir(parents=True)
    repair_prompt.write_text("return corrected JSON", encoding="utf-8")
    prompts: list[Path | None] = []
    valid_review = object()

    def run_phase(
        _run: Path,
        _phase: str,
        *,
        prompt_override: Path | None = None,
    ) -> object:
        prompts.append(prompt_override)
        if len(prompts) == 1:
            raise MvpError("Gemini response is not valid JSON")
        return valid_review

    monkeypatch.setattr(cli, "run_operator_phase", run_phase)
    monkeypatch.setattr(cli, "_validate_operator_review", lambda *_args: None, raising=False)
    monkeypatch.setattr(
        cli,
        "_write_critic_repair_prompt",
        lambda *_args, **_kwargs: repair_prompt,
        raising=False,
    )
    monkeypatch.setattr(cli, "_accept_operator_review", lambda *_args: 0)

    assert cli._gemini_web_run(run, "script") == 0
    assert prompts == [None, repair_prompt]
    assert read_state(run).stage is Stage.CHO_GEMINI_SCRIPT


def test_gemini_web_repair_loop_stops_after_six_total_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-01"
    new_state(run, stage=Stage.VIET_LOI)
    calls = 0

    def run_phase(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return object()

    def reject(*_args: object) -> None:
        raise MvpError("critic review lacks engine SOURCE anchors")

    def write_prompt(
        _run: Path,
        _phase: str,
        _error: MvpError,
        *,
        turn_number: int,
    ) -> Path:
        path = run / f"repair-{turn_number}.txt"
        path.write_text("repair", encoding="utf-8")
        return path

    monkeypatch.setattr(cli, "run_operator_phase", run_phase)
    monkeypatch.setattr(cli, "_validate_operator_review", reject)
    monkeypatch.setattr(cli, "_write_critic_repair_prompt", write_prompt)

    assert cli._gemini_web_run(run, "script") == 1
    assert calls == 6
    assert read_state(run).stage is Stage.CAN_CON_NGUOI_XU_LY


def test_operator_new_chat_replaces_stale_managed_chrome_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-01"
    run.mkdir(parents=True)
    (run / "gemini_web").mkdir()
    prompt = run / "prompt.txt"
    prompt.write_text("review this", encoding="utf-8")
    media = run / "proxy.mp4"
    media.write_bytes(b"proxy")
    registry = GeminiSessionRegistry(tmp_path / ".local" / "gemini_operator_session.json")
    registry.save(
        GeminiSessionMetadata(
            run.name,
            27776,
            "127.0.0.1:53198",
            "https://gemini.google.com/app/stale-chat",
            "2026-08-29T19:21:47+00:00",
            {"PROXY": 4},
        )
    )

    class Launch:
        chrome_pid = 456
        debugger_address = "127.0.0.1:9333"
        page = object()

        def __init__(self) -> None:
            self.detached = False

        def detach(self) -> None:
            self.detached = True

    launch = Launch()
    monkeypatch.setattr(gemini_session, "_pid_is_alive", lambda _pid: False)
    monkeypatch.setattr(gemini_session, "_debugger_is_alive", lambda _address: False)
    monkeypatch.setattr(cli, "launch_managed_chrome", lambda _root: launch)
    monkeypatch.setattr(
        cli,
        "connect_managed_chrome",
        lambda _metadata: pytest.fail("stale Chrome must not be reattached"),
    )
    monkeypatch.setattr(
        cli,
        "build_browser_packet",
        lambda *_args: SimpleNamespace(
            media_path=str(media),
            packet_sha256="a" * 64,
            prompt_path=str(prompt),
            upload_paths=(),
        ),
    )
    monkeypatch.setattr(
        cli,
        "load_profile_binding",
        lambda _path: SimpleNamespace(
            account_hint="u***@example.com", account_sha256="b" * 64
        ),
    )
    monkeypatch.setattr(cli, "_operator_ledger", lambda _run: object())
    monkeypatch.setattr(cli, "issue_request", lambda *_args: object())
    monkeypatch.setattr(cli, "calculate_policy_sha256", lambda _root: "c" * 64)
    monkeypatch.setattr(cli, "dump_json", lambda *_args: None)
    def successful_browser_session(*_args: object, **kwargs: object) -> object:
        kwargs["on_prompt_submitted"]()
        return SimpleNamespace(
            observation=SimpleNamespace(
                conversation_url="https://gemini.google.com/app/new-chat"
            )
        )

    monkeypatch.setattr(cli, "run_gemini_session", successful_browser_session)
    monkeypatch.setattr(
        cli,
        "load_operator_verified_review",
        lambda *_args, **_kwargs: object(),
    )

    class Operator:
        def __init__(self, **kwargs: object) -> None:
            self.session_runner = kwargs["session_runner"]

        def run(self, request: object, packet: object) -> None:
            self.session_runner(request, packet)

    monkeypatch.setattr(cli, "GeminiWebOperator", Operator)

    cli.run_operator_phase(run, "PROXY", force_new_chat=True)

    metadata = registry.load()
    assert metadata is not None
    assert metadata.chrome_pid == 456
    assert metadata.debugger_address == "127.0.0.1:9333"
    assert metadata.conversation_url == "https://gemini.google.com/app/new-chat"
    assert metadata.phase_turns == {"PROXY": 1}
    assert launch.detached is True


def test_operator_run_never_reuses_a_previous_browser_result_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-01"
    run.mkdir(parents=True)
    prompt = run / "prompt.txt"
    prompt.write_text("review this exact packet", encoding="utf-8")
    media = run / "proxy.mp4"
    media.write_bytes(b"proxy")
    checkpoint = (
        run
        / "gemini_web"
        / "proxy"
        / f"browser_result_{cli.sha256_file(prompt)}.json"
    )
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text('{"stale": true}', encoding="utf-8")
    registry = GeminiSessionRegistry(tmp_path / ".local" / "gemini_operator_session.json")
    registry.save(
        GeminiSessionMetadata(
            run.name,
            123,
            "127.0.0.1:9222",
            None,
            "2026-08-30T12:00:00+00:00",
            {},
        )
    )

    class Launch:
        chrome_pid = 123
        page = object()

        def detach(self) -> None:
            return None

    calls: list[str] = []
    monkeypatch.setattr(gemini_session, "_pid_is_alive", lambda _pid: True)
    monkeypatch.setattr(gemini_session, "_debugger_is_alive", lambda _address: True)
    monkeypatch.setattr(cli, "connect_managed_chrome", lambda _metadata: Launch())
    monkeypatch.setattr(
        cli,
        "build_browser_packet",
        lambda *_args: SimpleNamespace(
            media_path=str(media),
            packet_sha256="a" * 64,
            prompt_path=str(prompt),
            upload_paths=(),
        ),
    )
    monkeypatch.setattr(
        cli,
        "load_profile_binding",
        lambda _path: SimpleNamespace(
            account_hint="u***@example.com", account_sha256="b" * 64
        ),
    )
    monkeypatch.setattr(cli, "_operator_ledger", lambda _run: object())
    monkeypatch.setattr(cli, "issue_request", lambda *_args: object())
    monkeypatch.setattr(cli, "calculate_policy_sha256", lambda _root: "c" * 64)
    monkeypatch.setattr(cli, "dump_json", lambda *_args: None)
    monkeypatch.setattr(
        cli,
        "load_json",
        lambda *_args: pytest.fail("a browser checkpoint must never answer a new run"),
    )
    def fresh_browser_session(*_args: object, **kwargs: object) -> object:
        calls.append("browser")
        kwargs["on_prompt_submitted"]()
        return SimpleNamespace(
            observation=SimpleNamespace(
                conversation_url="https://gemini.google.com/app/fresh-result"
            )
        )

    monkeypatch.setattr(cli, "run_gemini_session", fresh_browser_session)
    monkeypatch.setattr(
        cli,
        "load_operator_verified_review",
        lambda *_args, **_kwargs: object(),
    )

    class Operator:
        def __init__(self, **kwargs: object) -> None:
            self.session_runner = kwargs["session_runner"]

        def run(self, request: object, packet: object) -> None:
            self.session_runner(request, packet)

    monkeypatch.setattr(cli, "GeminiWebOperator", Operator)

    cli.run_operator_phase(run, "PROXY")

    assert calls == ["browser"]


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
