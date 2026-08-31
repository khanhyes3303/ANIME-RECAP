from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from .adaptive_edl import AdaptiveEdlDocument, build_adaptive_edl
from .antigravity import (
    calculate_policy_sha256,
    load_audit,
    load_scene_packets,
    load_script,
    load_truth,
    render_operator_prompt,
)
from .atomic import load_atomic_storyboard, load_critic_review, validate_critic_evidence
from .audit import build_atomic_engine_audit, build_engine_audit
from .cue_audio import render_cue_audio_timeline
from .editor_provenance import (
    accept_antigravity_structure_submission,
    accept_antigravity_submission,
    create_editor_task,
    load_editor_ledger,
    load_editor_task,
)
from .editorial import load_locked_spans
from .edl import build_atomic_edl, build_edl_from_locked_spans
from .errors import MvpError
from .gemini_operator import (
    GeminiWebOperator,
    OperatorLedger,
    OperatorPolicy,
    issue_request,
    load_or_create_ledger_key,
)
from .gemini_packets import build_browser_packet
from .gemini_selenium import (
    ChromeLaunch,
    GeminiBrowserError,
    capture_existing_gemini_response,
    connect_managed_chrome,
    ensure_managed_chrome_visible,
    launch_managed_chrome,
    run_gemini_session,
)
from .gemini_session import (
    GeminiSessionMetadata,
    GeminiSessionRegistry,
    StaleGeminiSessionError,
)
from .gemini_web import (
    GeminiUltraProfileBinding,
    account_sha256,
    load_operator_verified_review,
    load_profile_binding,
    sha256_file,
    write_profile_binding,
)
from .jsonio import dump_json, load_json
from .local_audit import (
    build_episode_coherence_audit,
    build_local_audit,
    build_v2_local_audit,
    content_fingerprint,
    load_semantic_review,
)
from .media import (
    detect_shots,
    extract_adaptive_program_anchors,
    extract_atomic_source_anchors,
    extract_inspection_assets,
    extract_program_anchors,
    extract_situation_anchors,
    extract_span_anchors,
    preflight_media_tools,
    probe_source,
    transcribe_english,
)
from .models import (
    AtomicStoryboard,
    AtomicTtsManifest,
    CodexSemanticReview,
    CriticReviewDocument,
    FrameAnchorDocument,
    NarrationSpanDocument,
    ShotDocument,
    SourceRef,
    SpanEdlDocument,
    SpanTtsManifest,
    TranscriptDocument,
)
from .proxy_approval import approve_proxy, reject_proxy, require_approved_artifacts
from .render import RenderResult, render_review
from .semantic_timeline import SemanticTimeline, build_semantic_timeline
from .situation_index import load_situation_index, next_editable_situation
from .situation_packets import (
    build_scoped_situation_editor_packet,
    render_situation_editor_prompt,
)
from .situation_scope import (
    load_situation_scope,
    materialize_situation_scope,
    validate_submission_scope,
)
from .situation_validation import validate_narration_plan, validate_situations
from .situations import (
    CueTtsManifest,
    EditorialPolicy,
    NarrationClaim,
    NarrationPlan,
    NarrationUnit,
    Situation,
    SituationDocument,
    SituationTtsManifest,
    StoryContext,
    load_narration_plan,
    load_situations,
)
from .structure_packets import (
    build_structure_editor_packet,
    create_structure_task,
    render_structure_editor_prompt,
)
from .tts import (
    synthesize_atomic_beats,
    synthesize_narration_cues,
    synthesize_situation_units,
    synthesize_spans,
)
from .validation import (
    narration_style_findings,
    validate_scene_packets,
    validate_script,
    validate_truth,
)
from .workflow import (
    Stage,
    accept_editor_revision,
    accept_structure_index,
    advance,
    begin_editor_task,
    begin_verifier_task,
    begin_structure_task,
    fallback_to_legacy_observation,
    lock_editor_situation,
    lock_situation,
    mark_human_required,
    migrate_rejected_run,
    migrate_to_structure_index,
    new_state,
    read_state,
    record_beat_repair,
    record_local_repair,
    record_repair,
    record_stage_metric,
    resume_beat_repair,
    resume_browser_review,
    route_editor_repair,
)
from .workspace import assert_inside_run, create_job, publish_candidate
from .operator import OperatorDirective, plan_operator_step
from .review_packets import (
    build_situation_audit_packet,
    render_situation_audit_prompt,
    validate_situation_audit,
)
from .review_contracts import SituationAuditDocument


def _elapsed_ms(started: float) -> int:
    return max(1, round((time.perf_counter() - started) * 1_000))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_episode.py", description="Review đúng một tập anime bằng Antigravity"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Tạo job cho đúng một video")
    start.add_argument("--anime", required=True)
    start.add_argument("--season", required=True, type=int)
    start.add_argument("--episode", required=True, type=int)
    start.add_argument("--video", required=True, type=Path)
    start.add_argument("--revision", action="store_true")
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--run", required=True, type=Path)
    prompt = subparsers.add_parser("prompt", help="Tạo prompt đã gắn đúng đường dẫn run")
    prompt.add_argument("--run", required=True, type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--run", required=True, type=Path)
    validate.add_argument(
        "--artifact",
        required=True,
        choices=(
            "truth",
            "scene",
            "storyboard",
            "script",
            "edl",
            "situations",
            "narration",
            "semantic-review",
        ),
    )
    lock = subparsers.add_parser("lock")
    lock.add_argument("--run", required=True, type=Path)
    tts = subparsers.add_parser("tts")
    tts.add_argument("--run", required=True, type=Path)
    tts.add_argument("--situation")
    render = subparsers.add_parser("render")
    render.add_argument("--run", required=True, type=Path)
    render.add_argument("--quality", choices=("proxy", "final"), default="final")
    resume = subparsers.add_parser("resume")
    resume.add_argument("--run", required=True, type=Path)
    resume.add_argument("--phase", required=True, choices=("script", "tts", "video"))
    audit = subparsers.add_parser("audit")
    audit.add_argument("--run", required=True, type=Path)
    audit.add_argument(
        "--phase",
        required=True,
        choices=("script", "video", "local", "situation", "episode", "proxy", "engine"),
    )
    audit.add_argument("--codex-review", type=Path)
    gemini_web = subparsers.add_parser(
        "gemini-web", help="Audit Gemini Web tùy chọn cho run legacy; không thuộc luồng mặc định"
    )
    gemini_web.add_argument(
        "action",
        choices=("enroll", "smoke", "run", "new-chat", "continue", "show", "stop"),
    )
    gemini_web.add_argument("--run", required=True, type=Path)
    gemini_web.add_argument("--phase", choices=("script", "proxy", "final"))
    gemini_web.add_argument("--account-hint")
    gemini_web.add_argument("--prompt-file", type=Path)
    migrate = subparsers.add_parser("migrate-run")
    migrate.add_argument("--run", required=True, type=Path)
    migrate.add_argument(
        "--reason",
        required=True,
        choices=("user-rejected", "require-situation-index", "autonomous-operator"),
    )
    editor_task = subparsers.add_parser("editor-task")
    editor_task.add_argument("--run", required=True, type=Path)
    structure_task = subparsers.add_parser("structure-task")
    structure_task.add_argument("--run", required=True, type=Path)
    accept_index = subparsers.add_parser("accept-situation-index")
    accept_index.add_argument("--run", required=True, type=Path)
    accept_index.add_argument("--task", required=True)
    accept_index.add_argument("--input", required=True, type=Path)
    accept_editor = subparsers.add_parser("accept-antigravity")
    accept_editor.add_argument("--run", required=True, type=Path)
    accept_editor.add_argument("--task", required=True)
    accept_editor.add_argument("--input", required=True, type=Path)
    timeline = subparsers.add_parser("timeline")
    timeline.add_argument("--run", required=True, type=Path)
    timeline.add_argument("--situation")
    approve = subparsers.add_parser("approve-proxy")
    approve.add_argument("--run", required=True, type=Path)
    reject = subparsers.add_parser("reject-proxy")
    reject.add_argument("--run", required=True, type=Path)
    reject.add_argument("--note", required=True)
    reject.add_argument("--situation", required=True, action="append")
    operator = subparsers.add_parser(
        "operator", help="Tiếp tục luồng Antigravity theo các thẻ goal/teamwork-preview"
    )
    operator.add_argument("--run", required=True, type=Path)
    verifier_task = subparsers.add_parser("verifier-task")
    verifier_task.add_argument("--run", required=True, type=Path)
    verifier_task.add_argument("--kind", required=True, choices=("situation",))
    accept_verifier = subparsers.add_parser("accept-verifier")
    accept_verifier.add_argument("--run", required=True, type=Path)
    accept_verifier.add_argument("--task", required=True)
    accept_verifier.add_argument("--input", required=True, type=Path)
    return parser


def _start(args: argparse.Namespace) -> int:
    root = Path.cwd()
    paths = create_job(
        root,
        args.anime,
        args.season,
        args.episode,
        args.video,
        revision=args.revision,
    )
    state = new_state(
        paths.temp_dir,
        episode_dir=paths.episode_dir,
        source_video=paths.source_video,
    )
    next_action = {
        "stage": state.stage.value,
        "instruction": "Đọc Bo_nao_Antigravity/GEMINI.md rồi chạy bước prepare.",
        "run_dir": str(state.run_dir),
    }
    (state.run_dir / "next_action.json").write_text(
        json.dumps(next_action, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(state.run_dir)
    return 0


def _episode(run_dir: Path) -> tuple[object, Path]:
    state = read_state(run_dir)
    if not state.episode_dir:
        raise MvpError("run state has no episode directory")
    return state, Path(state.episode_dir)


def _write_next(run_dir: Path, instruction: str, *, code: str | None = None) -> None:
    state = read_state(run_dir)
    payload = {
        "stage": state.stage.value,
        "instruction": instruction,
        "run_dir": str(state.run_dir),
    }
    if code is not None:
        payload["code"] = code
    (run_dir / "next_action.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _operator_editable_ids(run_dir: Path) -> tuple[str, ...]:
    """Read editable situation IDs without imposing a fixed situation count."""
    path = run_dir / "situation_index.json"
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    entries = payload.get("situations", payload) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        return ()
    result: list[str] = []
    for item in entries:
        if not isinstance(item, dict) or item.get("excluded") is True:
            continue
        situation_id = item.get("situation_id") or item.get("id")
        if isinstance(situation_id, str) and situation_id.strip():
            result.append(situation_id.strip())
    return tuple(result)


def _operator_command(run_dir: Path) -> int:
    """Execute local deterministic preparation until a human/Antigravity gate."""
    state = read_state(run_dir)
    if state.stage is Stage.CHUAN_BI:
        _prepare(run_dir)
        state = read_state(run_dir)
    directive = plan_operator_step(
        state, editable_ids=_operator_editable_ids(run_dir)
    )
    if directive.action == "PREPARE_STRUCTURE_JOB":
        _structure_task_command(run_dir)
        state = read_state(run_dir)
    elif directive.action == "PREPARE_SITUATION_JOB":
        # The accepted index already records the next situation.  The editor
        # command performs all scope/hash checks before exposing a job.
        _editor_task_command(run_dir)
        state = read_state(run_dir)
    try:
        next_payload = json.loads(
            (run_dir / "next_action.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        next_payload = {}
    status = {
        "action": directive.action,
        "stage": state.stage.value,
        "task_id": state.editor_task_id or state.verifier_task_id,
        "instruction": next_payload.get("instruction", ""),
    }
    if directive.situation_id:
        status["situation_id"] = directive.situation_id
    if directive.stop_code:
        status["stop_code"] = directive.stop_code
    (run_dir / "operator_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(run_dir / "operator_status.json")
    return 0


def _verifier_task_command(run_dir: Path, kind: str) -> int:
    if kind != "situation":
        raise MvpError("unsupported verifier task kind")
    state, episode = _episode(run_dir)
    if state.stage is not Stage.CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG:
        raise MvpError("verifier-task requires situation verifier wait stage")
    if not state.current_situation_id or not state.editor_task_id:
        raise MvpError("verifier-task requires active producer situation task")
    producer = load_editor_task(run_dir / "editor_tasks" / f"{state.editor_task_id}.json")
    scope = load_situation_scope(
        run_dir / "situation_inputs" / state.current_situation_id / "scope.json",
        verify_files=True,
    )
    plan = load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
    verifier = create_editor_task(
        run_dir,
        run_dir.name,
        state.current_situation_id,
        max(1, state.editorial_revision),
        tuple(Path(path) for path in scope.input_paths),
        task_kind="SITUATION_AUDIT",
        allowed_outputs=("situation_audit_draft.json",),
        expected_stage="ANTIGRAVITY_VERIFIER",
    )
    begin_verifier_task(run_dir, verifier.task_id, verifier.situation_id, verifier.revision)
    packet = build_situation_audit_packet(scope, plan, producer, verifier)
    dump_json(run_dir / "cong_viec_antigravity.json", packet)
    (run_dir / "PROMPT_GUI_ANTIGRAVITY.txt").write_text(
        render_situation_audit_prompt(packet), encoding="utf-8"
    )
    _write_next(
        run_dir,
        f"Verifier kiểm tra từng cue của {packet.situation_id}; chỉ ghi situation_audit_draft.json rồi chạy accept-verifier --run "
        f'"{run_dir}" --task {verifier.task_id} --input "{run_dir / "editor_staging" / verifier.task_id}".',
    )
    print(run_dir / "cong_viec_antigravity.json")
    return 0


def _accept_verifier_command(run_dir: Path, task_id: str, staging_dir: Path) -> int:
    state, episode = _episode(run_dir)
    task = load_editor_task(run_dir / "editor_tasks" / f"{task_id}.json")
    if task.task_kind != "SITUATION_AUDIT" or state.verifier_task_id != task_id:
        raise MvpError("verifier task does not match the active task")
    audit_path = staging_dir / "situation_audit_draft.json"
    audit = load_json(audit_path, SituationAuditDocument)
    plan = load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
    scope = load_situation_scope(
        run_dir / "situation_inputs" / task.situation_id / "scope.json", verify_files=True
    )
    if audit.situation_id != task.situation_id:
        raise MvpError("VERIFIER_SITUATION_SCOPE_INVALID")
    try:
        validate_situation_audit(audit, plan)
    except MvpError:
        codes = tuple(dict.fromkeys(code for item in audit.cue_reviews for code in item.finding_codes)) or ("SITUATION_AUDIT_FAILED",)
        advance(run_dir, Stage.CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG, Stage.KIEM_DINH_PHAN_BIEN_TINH_HUONG)
        route_verifier_repair(run_dir, task.situation_id, codes, content_fingerprint((audit_path,)))
        _write_next(run_dir, f"Verifier phát hiện lỗi ở {task.situation_id}; Antigravity sửa rồi chạy editor-task lại.")
        return 1
    # A successful verifier is independently recorded before the situation is locked.
    ledger = run_dir / "verifier_ledger.jsonl"
    from .jsonio import atomic_append_jsonl
    from .editor_provenance import AcceptedVerifierRevision
    accepted = AcceptedVerifierRevision(
        task.task_id, task.run_id, task.task_kind, task.situation_id, task.revision,
        "ANTIGRAVITY_VERIFIER", task.input_sha256, content_fingerprint((audit_path,))
    )
    atomic_append_jsonl(ledger, accepted)
    advance(run_dir, Stage.CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG, Stage.KIEM_DINH_PHAN_BIEN_TINH_HUONG)
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    index = load_situation_index(run_dir / "situation_index.json", source, load_json(run_dir / "transcript_english.json", TranscriptDocument), load_json(run_dir / "shots.json", ShotDocument), _frame_refs(run_dir))
    following = next_editable_situation(index, (*state.locked_situation_ids, task.situation_id))
    lock_editor_situation(run_dir, task.situation_id, next_situation_id="" if following is None else following.situation_id)
    _write_next(run_dir, "Verifier đạt MATCH; tình huống đã khóa và operator có thể tiếp tục.")
    return 0


def _prepare(run_dir: Path) -> int:
    state, episode = _episode(run_dir)
    if state.stage is not Stage.CHUAN_BI:
        raise MvpError("prepare requires CHUAN_BI stage")
    try:
        preflight_media_tools()
    except MvpError as exc:
        _write_next(run_dir, str(exc), code="THIEU_CONG_CU")
        raise
    source = probe_source(Path(state.source_video))
    dump_json(episode / "Dau_vao" / "source_ref.json", source)
    paths = _job_paths_from_state(state, episode)
    source_cache = paths.cache_dir / "source" / source.sha256
    source_cache.mkdir(parents=True, exist_ok=True)
    transcript_cache = source_cache / "transcript_english.json"
    shots_cache = source_cache / "shots.json"
    frames_cache = source_cache / "frames"
    if transcript_cache.is_file():
        transcript = load_json(transcript_cache, TranscriptDocument)
    else:
        transcript = transcribe_english(Path(state.source_video), transcript_cache)
    if shots_cache.is_file():
        shots = load_json(shots_cache, ShotDocument).shots
    else:
        shots = detect_shots(Path(state.source_video), source.duration_ms)
        dump_json(shots_cache, ShotDocument(shots))
    if not frames_cache.is_dir() or not any(frames_cache.glob("*.jpg")):
        extract_inspection_assets(Path(state.source_video), shots, frames_cache)
    dump_json(run_dir / "transcript_english.json", transcript)
    dump_json(run_dir / "shots.json", ShotDocument(shots))
    frame_manifest_path = run_dir / "frame_manifest.json"
    frame_manifest_path.write_text(
        json.dumps(
            {
                "frames": [str(path.resolve()) for path in sorted(frames_cache.glob("*.jpg"))]
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    advance(run_dir, Stage.CHUAN_BI, Stage.TRICH_XUAT_BANG_CHUNG)
    advance(
        run_dir,
        Stage.TRICH_XUAT_BANG_CHUNG,
        Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG,
    )
    return _structure_task_command(run_dir)


def _job_paths_from_state(state: object, episode: Path):
    from .workspace import JobKey, JobPaths

    season = int(episode.parent.name.removeprefix("Mua_"))
    episode_number = int(episode.name.removeprefix("Tap_"))
    anime = episode.parents[1].name
    return JobPaths(
        root=episode.parents[3],
        key=JobKey(anime, season, episode_number),
        source_video=Path(state.source_video),
        episode_dir=episode,
        input_dir=episode / "Dau_vao",
        truth_dir=episode / "Su_that",
        script_dir=episode / "Kich_ban",
        tts_dir=episode / "TTS",
        edl_dir=episode / "Ke_hoach_canh",
        final_dir=episode / "Thanh_pham",
        report_dir=episode / "Bao_cao",
        temp_dir=Path(state.run_dir),
    )


def _editorial_policy(episode: Path) -> EditorialPolicy:
    policy_path = episode / "Ke_hoach_canh" / "editorial_policy.json"
    if not policy_path.is_file():
        return EditorialPolicy()
    try:
        return EditorialPolicy(**json.loads(policy_path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise MvpError(f"cannot load editorial policy: {policy_path}") from exc


def _validate(run_dir: Path, artifact: str) -> int:
    started = time.perf_counter()
    state, episode = _episode(run_dir)
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    if artifact == "truth":
        truth = load_truth(
            episode / "Su_that" / "su_that_tap_phim.json",
            source_duration_ms=source.duration_ms,
        )
        validate_truth(truth, source.duration_ms)
        if state.stage in {
            Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG,
            Stage.CHO_ANTIGRAVITY_TINH_HUONG,
        }:
            state = fallback_to_legacy_observation(run_dir)
        if state.stage is Stage.QUAN_SAT:
            advance(run_dir, Stage.QUAN_SAT, Stage.LAP_TINH_HUONG)
            _write_next(
                run_dir,
                "Lập situations.json từ transcript + frame rồi chạy "
                "validate --artifact situations.",
            )
        else:
            _write_next(run_dir, "Kiểm tra scene_packets.json rồi chạy validate --artifact scene.")
    elif artifact == "situations":
        if state.stage is not Stage.LAP_TINH_HUONG:
            raise MvpError("situation validation requires LAP_TINH_HUONG stage")
        truth = load_truth(
            episode / "Su_that" / "su_that_tap_phim.json",
            source_duration_ms=source.duration_ms,
        )
        shots = load_json(run_dir / "shots.json", ShotDocument)
        situations = load_situations(episode / "Kich_ban" / "situations.json")
        validate_situations(
            situations,
            truth,
            shots.shots,
            source_duration_ms=source.duration_ms,
        )
        advance(run_dir, Stage.LAP_TINH_HUONG, Stage.VIET_LOI)
        _write_next(
            run_dir,
            "Viết narration_plan.json theo từng tình huống rồi chạy validate --artifact narration.",
        )
    elif artifact == "narration":
        if state.stage is not Stage.VIET_LOI:
            raise MvpError("narration validation requires VIET_LOI stage")
        truth = load_truth(
            episode / "Su_that" / "su_that_tap_phim.json",
            source_duration_ms=source.duration_ms,
        )
        shots = load_json(run_dir / "shots.json", ShotDocument)
        situations = load_situations(episode / "Kich_ban" / "situations.json")
        plan = load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
        validate_narration_plan(
            plan,
            situations,
            truth,
            shots.shots,
            _editorial_policy(episode),
            source.duration_ms,
        )
        extract_situation_anchors(
            Path(state.source_video),
            plan,
            run_dir / "local_evidence" / "source",
        )
        advance(run_dir, Stage.VIET_LOI, Stage.TAO_TTS)
        _write_next(run_dir, "Narration đạt; tạo TTS và adaptive EDL.")
    elif artifact == "semantic-review":
        if state.stage is not Stage.KIEM_DINH_LOCAL:
            raise MvpError("semantic review validation requires KIEM_DINH_LOCAL stage")
        plan = load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
        source_anchors = load_json(
            run_dir / "local_evidence" / "source" / "anchors.json",
            FrameAnchorDocument,
        )
        program_anchors = load_json(
            run_dir / "local_evidence" / "program" / "anchors.json",
            FrameAnchorDocument,
        )
        load_semantic_review(
            episode / "Bao_cao" / "local_semantic_review.json",
            plan,
            source_anchors,
            program_anchors,
        )
        _write_next(run_dir, "Semantic review hợp lệ; chạy audit --phase local.")
    elif artifact == "scene":
        if state.stage not in {Stage.QUAN_SAT, Stage.LAP_TINH_HUONG}:
            raise MvpError("scene validation requires a legacy observation stage")
        truth = load_truth(
            episode / "Su_that" / "su_that_tap_phim.json",
            source_duration_ms=source.duration_ms,
        )
        packets = load_scene_packets(episode / "Su_that" / "scene_packets.json")
        shots_path = run_dir / "shots.json"
        if shots_path.is_file():
            shots = load_json(shots_path, ShotDocument)
        else:
            # Runs prepared by the pre-scene contract can still be resumed safely.
            shots = ShotDocument(detect_shots(Path(state.source_video), source.duration_ms))
            dump_json(shots_path, shots)
        validate_scene_packets(packets.packets, truth, shots.shots, source.duration_ms)
        advance(run_dir, state.stage, Stage.LAP_STORYBOARD)
        _write_next(
            run_dir,
            "Antigravity lập atomic_storyboard.json từ scene, shot và frame bằng chứng.",
        )
    elif artifact == "storyboard":
        if state.stage is not Stage.LAP_STORYBOARD:
            raise MvpError("storyboard validation requires LAP_STORYBOARD stage")
        truth = load_truth(
            episode / "Su_that" / "su_that_tap_phim.json",
            source_duration_ms=source.duration_ms,
        )
        shots = load_json(run_dir / "shots.json", ShotDocument)
        storyboard = load_atomic_storyboard(
            episode / "Kich_ban" / "atomic_storyboard.json",
            truth,
            shots.shots,
            source.duration_ms,
        )
        extract_atomic_source_anchors(
            Path(state.source_video),
            storyboard,
            run_dir / "atomic_evidence" / "source",
        )
        record_stage_metric(
            run_dir,
            Stage.LAP_STORYBOARD,
            _elapsed_ms(started),
            0,
            0,
            tuple(beat.beat_id for beat in storyboard.beats),
        )
        advance(run_dir, Stage.LAP_STORYBOARD, Stage.VIET_LOI)
        _write_next(
            run_dir,
            "Antigravity hoàn thiện lời theo atomic beat rồi tạo critic-script độc lập.",
        )
    elif artifact == "script":
        truth = load_truth(
            episode / "Su_that" / "su_that_tap_phim.json",
            source_duration_ms=source.duration_ms,
        )
        script = load_script(episode / "Kich_ban" / "kich_ban_review.json")
        validate_script(script, truth)
        advance(run_dir, Stage.VIET_KICH_BAN, Stage.KIEM_DINH_KICH_BAN)
        _write_next(run_dir, "KIEM_DINH kịch bản và ghi kiem_dinh.json.")
    else:
        if state.stage is Stage.CAN_HINH_VOICE:
            plan = load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
            tts = load_json(
                episode / "TTS" / "situation_tts_manifest.json",
                SituationTtsManifest,
            )
            edl = load_json(
                episode / "Ke_hoach_canh" / "adaptive_edl.json",
                AdaptiveEdlDocument,
            )
            expected = build_adaptive_edl(
                plan,
                tts,
                source_duration_ms=source.duration_ms,
                policy=_editorial_policy(episode),
            )
            if edl != expected:
                raise MvpError("persisted adaptive EDL does not match narration and TTS")
            situation_ids = tuple(dict.fromkeys(unit.situation_id for unit in plan.units))
            for index, situation_id in enumerate(situation_ids):
                next_id = situation_ids[index + 1] if index + 1 < len(situation_ids) else ""
                lock_situation(run_dir, situation_id, next_situation_id=next_id)
            advance(run_dir, Stage.CAN_HINH_VOICE, Stage.DUNG_PROXY)
            _write_next(run_dir, "Tình huống đã khóa; render --quality proxy.")
            return 0
        if state.stage is Stage.CAN_TTS:
            storyboard = load_json(
                episode / "Kich_ban" / "atomic_storyboard.json", AtomicStoryboard
            )
            tts = load_json(episode / "TTS" / "atomic_tts_manifest.json", AtomicTtsManifest)
            edl = load_json(episode / "Ke_hoach_canh" / "atomic_edl.json", SpanEdlDocument)
            if edl != build_atomic_edl(storyboard, tts):
                raise MvpError("persisted atomic EDL does not match storyboard and TTS")
            advance(run_dir, Stage.CAN_TTS, Stage.DUNG_PROXY)
            _write_next(run_dir, "Atomic EDL đạt; render --quality proxy.")
            return 0
        truth = load_truth(
            episode / "Su_that" / "su_that_tap_phim.json",
            source_duration_ms=source.duration_ms,
        )
        locked = load_locked_spans(
            episode / "Kich_ban" / "khoa_cau_canh.json",
            truth,
            source.duration_ms,
        )
        tts = load_json(episode / "TTS" / "span_tts_manifest.json", SpanTtsManifest)
        edl = load_json(episode / "Ke_hoach_canh" / "edl.json", SpanEdlDocument)
        if edl != build_edl_from_locked_spans(locked, tts):
            raise MvpError("persisted EDL does not match Codex locked spans")
        advance(run_dir, Stage.LAP_EDL, Stage.DUNG_VIDEO)
        _write_next(run_dir, "Codex chạy render để dựng candidate TTS-only.")
    return 0


def _lock(run_dir: Path) -> int:
    state, episode = _episode(run_dir)
    if state.stage is not Stage.CODEX_BIEN_TAP:
        raise MvpError("lock requires CODEX_BIEN_TAP stage")
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    truth = load_truth(
        episode / "Su_that" / "su_that_tap_phim.json",
        source_duration_ms=source.duration_ms,
    )
    locked = load_locked_spans(
        episode / "Kich_ban" / "khoa_cau_canh.json",
        truth,
        source.duration_ms,
    )
    extract_span_anchors(
        Path(state.source_video),
        locked,
        run_dir / "codex_evidence" / "source",
        timeline="SOURCE",
    )
    advance(run_dir, Stage.CODEX_BIEN_TAP, Stage.TAO_TTS)
    _write_next(run_dir, "Khóa câu-cảnh đạt; Codex chạy TTS theo span.")
    return 0


def _tts(run_dir: Path, situation_id: str | None = None) -> int:
    started = time.perf_counter()
    state, episode = _episode(run_dir)
    if state.stage is Stage.TAO_TTS_TINH_HUONG:
        source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
        plan = load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
        manifest = synthesize_narration_cues(
            plan,
            run_dir / "cue_tts",
            episode / "_Cache" / "cue_tts",
            source_sha256=source.sha256,
        )
        dump_json(run_dir / "cue_tts_manifest.json", manifest)
        advance(
            run_dir,
            Stage.TAO_TTS_TINH_HUONG,
            Stage.LAP_TIMELINE_TINH_HUONG,
        )
        _write_next(run_dir, "TTS từng cue đã tạo; chạy timeline --run RUN_DIR.")
        return 0
    if state.stage is not Stage.TAO_TTS:
        raise MvpError("tts requires TAO_TTS or TAO_TTS_TINH_HUONG stage")
    situation_plan_path = episode / "Kich_ban" / "narration_plan.json"
    if situation_plan_path.is_file():
        source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
        plan = load_narration_plan(situation_plan_path)
        situation_ids = tuple(dict.fromkeys(unit.situation_id for unit in plan.units))
        if situation_id is not None and situation_id not in situation_ids:
            raise MvpError(f"unknown situation ID: {situation_id}")
        tts = synthesize_situation_units(
            plan,
            episode / "TTS",
            episode / "_Cache" / "situation_tts",
            source_sha256=source.sha256,
        )
        edl = build_adaptive_edl(
            plan,
            tts,
            source_duration_ms=source.duration_ms,
            policy=_editorial_policy(episode),
        )
        dump_json(episode / "Ke_hoach_canh" / "adaptive_edl.json", edl)
        record_stage_metric(
            run_dir,
            Stage.TAO_TTS,
            _elapsed_ms(started),
            tts.cache_hits,
            tts.cache_misses,
            situation_ids,
        )
        advance(run_dir, Stage.TAO_TTS, Stage.CAN_HINH_VOICE)
        _write_next(
            run_dir,
            f"TTS cache: {tts.cache_hits} hit, {tts.cache_misses} miss; "
            "chạy validate --artifact edl để khóa từng tình huống.",
        )
        return 0
    atomic_path = episode / "Kich_ban" / "atomic_storyboard.json"
    if atomic_path.is_file():
        source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
        truth = load_truth(
            episode / "Su_that" / "su_that_tap_phim.json",
            source_duration_ms=source.duration_ms,
        )
        shots = load_json(run_dir / "shots.json", ShotDocument)
        storyboard = load_atomic_storyboard(
            atomic_path,
            truth,
            shots.shots,
            source.duration_ms,
        )
        tts = synthesize_atomic_beats(
            storyboard,
            episode / "TTS",
            episode / "_Cache" / "tts",
            revision_id=run_dir.resolve().name,
            source_sha256=source.sha256,
        )
        edl = build_atomic_edl(storyboard, tts)
        dump_json(episode / "Ke_hoach_canh" / "atomic_edl.json", edl)
        record_stage_metric(
            run_dir,
            Stage.TAO_TTS,
            _elapsed_ms(started),
            tts.cache_stats.hits,
            tts.cache_stats.misses,
            tuple(beat.beat_id for beat in storyboard.beats if beat.actual_tts_ms is None),
        )
        advance(run_dir, Stage.TAO_TTS, Stage.CAN_TTS)
        _write_next(
            run_dir,
            f"TTS cache: {tts.cache_stats.hits} hit, {tts.cache_stats.misses} miss; "
            "chạy validate --artifact edl.",
        )
        return 0
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    truth = load_truth(
        episode / "Su_that" / "su_that_tap_phim.json",
        source_duration_ms=source.duration_ms,
    )
    locked = load_locked_spans(
        episode / "Kich_ban" / "khoa_cau_canh.json",
        truth,
        source.duration_ms,
    )
    tts = synthesize_spans(locked, episode / "TTS")
    edl = build_edl_from_locked_spans(locked, tts)
    dump_json(episode / "Ke_hoach_canh" / "edl.json", edl)
    advance(run_dir, Stage.TAO_TTS, Stage.LAP_EDL)
    _write_next(
        run_dir,
        "EDL giữ nguyên range Codex và duration TTS thật; chạy validate --artifact edl.",
    )
    return 0


def _render(run_dir: Path, quality: str = "final") -> int:
    started = time.perf_counter()
    state, episode = _episode(run_dir)
    if (
        quality == "final"
        and state.stage is Stage.DUNG_VIDEO_CUOI
        and state.editorial_revision >= 1
    ):
        require_approved_artifacts(run_dir)
    v2_adaptive_path = run_dir / "adaptive_edl.json"
    adaptive_path = (
        v2_adaptive_path
        if state.editorial_revision >= 1 and v2_adaptive_path.is_file()
        else episode / "Ke_hoach_canh" / "adaptive_edl.json"
    )
    if adaptive_path.is_file() and quality == "proxy" and state.stage is Stage.DUNG_PROXY:
        edl = load_json(adaptive_path, AdaptiveEdlDocument)
        narration_path = run_dir / "aligned_narration.wav"
        if state.editorial_revision >= 1:
            if not narration_path.is_file():
                raise MvpError("aligned narration audio is missing")
        else:
            tts = load_json(
                episode / "TTS" / "situation_tts_manifest.json",
                SituationTtsManifest,
            )
            narration_path = Path(tts.narration_wav_path)
        output = run_dir / "proxy" / "review_proxy.mp4"
        result = render_review(
            Path(state.source_video),
            narration_path,
            edl,
            output,
            quality="proxy",
        )
        dump_json(run_dir / "proxy" / "render_result.json", result)
        extract_adaptive_program_anchors(
            output,
            edl,
            run_dir / "local_evidence" / "program",
        )
        record_stage_metric(run_dir, Stage.DUNG_PROXY, _elapsed_ms(started), 0, 0, ())
        if state.editorial_revision >= 1:
            advance(run_dir, Stage.DUNG_PROXY, Stage.KIEM_DINH_PROXY)
            _write_next(run_dir, "Proxy đã dựng; chạy audit --phase proxy.")
        else:
            advance(run_dir, Stage.DUNG_PROXY, Stage.KIEM_DINH_LOCAL)
            _write_next(
                run_dir,
                "Proxy đã dựng; ghi local_semantic_review.json rồi chạy audit --phase local.",
            )
        print(output)
        return 0
    if (
        adaptive_path.is_file()
        and quality == "final"
        and state.stage is Stage.DUNG_VIDEO_CUOI
    ):
        edl = load_json(adaptive_path, AdaptiveEdlDocument)
        narration_path = run_dir / "aligned_narration.wav"
        if state.editorial_revision >= 1:
            if not narration_path.is_file():
                raise MvpError("aligned narration audio is missing")
        else:
            tts = load_json(
                episode / "TTS" / "situation_tts_manifest.json",
                SituationTtsManifest,
            )
            narration_path = Path(tts.narration_wav_path)
        output = run_dir / "final_candidate.mp4"
        result = render_review(
            Path(state.source_video),
            narration_path,
            edl,
            output,
            quality="final",
        )
        dump_json(run_dir / "final_render_result.json", result)
        extract_adaptive_program_anchors(
            output,
            edl,
            run_dir / "local_evidence" / "program_final",
        )
        record_stage_metric(
            run_dir,
            Stage.DUNG_VIDEO_CUOI,
            _elapsed_ms(started),
            0,
            0,
            (),
        )
        advance(run_dir, Stage.DUNG_VIDEO_CUOI, Stage.KIEM_DINH_ENGINE)
        _write_next(run_dir, "Final candidate đã dựng; chạy audit --phase engine.")
        print(output)
        return 0
    if quality == "proxy" and state.stage is Stage.DUNG_PROXY:
        edl = load_json(episode / "Ke_hoach_canh" / "atomic_edl.json", SpanEdlDocument)
        tts = load_json(episode / "TTS" / "atomic_tts_manifest.json", AtomicTtsManifest)
        output = run_dir / "proxy" / "review_proxy.mp4"
        result = render_review(
            Path(state.source_video),
            Path(tts.narration_wav_path),
            edl,
            output,
            quality="proxy",
        )
        dump_json(run_dir / "proxy" / "render_result.json", result)
        extract_program_anchors(output, edl, run_dir / "atomic_evidence" / "program")
        record_stage_metric(
            run_dir,
            Stage.DUNG_PROXY,
            _elapsed_ms(started),
            0,
            0,
            (),
        )
        advance(run_dir, Stage.DUNG_PROXY, Stage.PHAN_BIEN_VIDEO)
        _write_next(
            run_dir,
            "Antigravity mở proxy và evidence, ghi critic_video.json bằng critic context khác.",
        )
        print(output)
        return 0
    if quality == "final" and state.stage is Stage.DUNG_VIDEO_CUOI:
        edl = load_json(episode / "Ke_hoach_canh" / "atomic_edl.json", SpanEdlDocument)
        tts = load_json(episode / "TTS" / "atomic_tts_manifest.json", AtomicTtsManifest)
        output = run_dir / "final_candidate.mp4"
        result = render_review(
            Path(state.source_video),
            Path(tts.narration_wav_path),
            edl,
            output,
            quality="final",
        )
        dump_json(run_dir / "final_render_result.json", result)
        extract_program_anchors(output, edl, run_dir / "atomic_evidence" / "program")
        record_stage_metric(
            run_dir,
            Stage.DUNG_VIDEO_CUOI,
            _elapsed_ms(started),
            0,
            0,
            (),
        )
        advance(run_dir, Stage.DUNG_VIDEO_CUOI, Stage.CHO_GEMINI_FINAL)
        _write_next(run_dir, "Final candidate đã dựng; chạy web-verify prepare --phase final.")
        print(output)
        return 0
    if state.stage is not Stage.DUNG_VIDEO:
        raise MvpError("render stage does not match requested quality")
    edl = load_json(episode / "Ke_hoach_canh" / "edl.json", SpanEdlDocument)
    tts = load_json(episode / "TTS" / "span_tts_manifest.json", SpanTtsManifest)
    output = run_dir / "review_candidate.mp4"
    result = render_review(Path(state.source_video), Path(tts.narration_wav_path), edl, output)
    dump_json(run_dir / "render_result.json", result)
    extract_program_anchors(output, edl, run_dir / "codex_evidence" / "program")
    advance(run_dir, Stage.DUNG_VIDEO, Stage.KIEM_DINH_VIDEO)
    _write_next(
        run_dir,
        "Codex xem anchor candidate, ghi codex_semantic_review.json rồi chạy audit video.",
    )
    print(output)
    return 0


def _audit_script(run_dir: Path, episode: Path) -> int:
    audit = load_audit(episode / "Bao_cao" / "kiem_dinh.json")
    script = load_script(episode / "Kich_ban" / "kich_ban_review.json")
    findings = narration_style_findings(script)
    blocking = tuple(finding.code for finding in audit.findings if finding.severity == "ERROR")
    blocking += tuple(finding.code for finding in findings)
    if not audit.passed or blocking:
        codes = blocking or ("AUDIT_NOT_PASSED",)
        state = record_repair(run_dir, "SUA_NOI_DUNG", codes)
        _write_next(run_dir, f"Antigravity sửa bản nháp; vòng {len(state.repair_history)}/3.")
        return 1
    advance(run_dir, Stage.KIEM_DINH_KICH_BAN, Stage.CODEX_BIEN_TAP)
    _write_next(run_dir, "Antigravity dừng; chuyển job và bản nháp cho Codex biên tập.")
    return 0


def _audit_video(run_dir: Path, episode: Path, codex_review: Path | None) -> int:
    if codex_review is None:
        raise MvpError("video audit requires --codex-review")
    expected_review = (episode / "Bao_cao_Codex" / "codex_semantic_review.json").resolve()
    if codex_review.resolve() != expected_review:
        raise MvpError("Codex review path must belong to this episode")
    locked = load_json(episode / "Kich_ban" / "khoa_cau_canh.json", NarrationSpanDocument)
    tts = load_json(episode / "TTS" / "span_tts_manifest.json", SpanTtsManifest)
    review = load_json(codex_review, CodexSemanticReview)
    source_anchors = load_json(
        run_dir / "codex_evidence" / "source" / "anchors.json", FrameAnchorDocument
    )
    program_anchors = load_json(
        run_dir / "codex_evidence" / "program" / "anchors.json", FrameAnchorDocument
    )
    render = load_json(run_dir / "render_result.json", RenderResult)
    report = build_engine_audit(locked, tts, review, source_anchors, program_anchors, render)
    dump_json(episode / "Bao_cao" / "kiem_dinh_engine.json", report)
    if not report.passed:
        codes = tuple(finding.code for finding in report.findings if finding.severity == "ERROR")
        scene_markers = ("SCENE", "EDL", "FOOTAGE", "DRIFT", "VOICE")
        owner = (
            "SUA_EDL"
            if any(marker in code for code in codes for marker in scene_markers)
            else "SUA_NOI_DUNG"
        )
        state = record_repair(run_dir, owner, codes)
        _write_next(
            run_dir,
            f"{owner}: sửa {', '.join(codes)}; vòng {len(state.repair_history)}/3.",
        )
        return 1
    publish_candidate(
        run_dir / "review_candidate.mp4",
        episode / "Thanh_pham" / "review_anime.mp4",
        episode / "Bao_cao" / "phien_ban_cu",
    )
    advance(
        run_dir,
        Stage.KIEM_DINH_VIDEO,
        Stage.HOAN_THANH,
        _engine_audit_passed=True,
    )
    _write_next(run_dir, "HOAN_THANH; giữ nguyên run và giao MP4 cho người dùng xem.")
    return 0


def _audit_atomic_engine(run_dir: Path, episode: Path) -> int:
    state = read_state(run_dir)
    if state.stage is not Stage.KIEM_DINH_ENGINE:
        raise MvpError("engine audit requires KIEM_DINH_ENGINE stage")
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    truth = load_truth(
        episode / "Su_that" / "su_that_tap_phim.json",
        source_duration_ms=source.duration_ms,
    )
    shots = load_json(run_dir / "shots.json", ShotDocument)
    storyboard = load_atomic_storyboard(
        episode / "Kich_ban" / "atomic_storyboard.json",
        truth,
        shots.shots,
        source.duration_ms,
    )
    tts = load_json(episode / "TTS" / "atomic_tts_manifest.json", AtomicTtsManifest)
    source_anchors = load_json(
        run_dir / "atomic_evidence" / "source" / "anchors.json",
        FrameAnchorDocument,
    )
    program_anchors = load_json(
        run_dir / "atomic_evidence" / "program" / "anchors.json",
        FrameAnchorDocument,
    )
    script_critic = _load_verified_critic(run_dir, "script", storyboard)
    validate_critic_evidence(script_critic, storyboard, source_anchors)
    proxy_critic = _load_verified_critic(run_dir, "proxy", storyboard)
    validate_critic_evidence(proxy_critic, storyboard, source_anchors, program_anchors)
    critic = _load_verified_critic(run_dir, "final", storyboard)
    render = load_json(run_dir / "final_render_result.json", RenderResult)
    job_payload = json.loads((run_dir / "cong_viec_antigravity.json").read_text(encoding="utf-8"))
    actual_hash = calculate_policy_sha256(episode.parents[3])
    expected_hash = job_payload.get("policy_sha256", actual_hash)
    report = build_atomic_engine_audit(
        storyboard,
        tts,
        critic,
        source_anchors,
        program_anchors,
        render,
        expected_policy_sha256=expected_hash,
        actual_policy_sha256=actual_hash,
        completed_stage_names=tuple(metric.stage for metric in state.stage_metrics),
    )
    dump_json(episode / "Bao_cao" / "kiem_dinh_engine.json", report)
    if not report.passed:
        errors = tuple(item for item in report.findings if item.severity == "ERROR")
        beat_ids = tuple(
            dict.fromkeys(item.cue_id for item in errors if item.cue_id is not None)
        ) or tuple(beat.beat_id for beat in storyboard.beats)
        codes = tuple(dict.fromkeys(item.code for item in errors))
        repaired = record_beat_repair(run_dir, "VIDEO", beat_ids, codes)
        _write_next(
            run_dir,
            f"Engine chặn {', '.join(codes)}; chỉ sửa beat liên quan, vòng "
            f"{len(repaired.repair_history)}/3.",
        )
        return 1
    publish_candidate(
        run_dir / "final_candidate.mp4",
        episode / "Thanh_pham" / "review_anime.mp4",
        episode / "Bao_cao" / "phien_ban_cu",
    )
    advance(
        run_dir,
        Stage.KIEM_DINH_ENGINE,
        Stage.HOAN_THANH,
        _engine_audit_passed=True,
    )
    _write_next(run_dir, "HOAN_THANH; giao review_anime.mp4 cho người dùng xem.")
    return 0


def _audit_local(run_dir: Path, episode: Path, *, final: bool = False) -> int:
    state = read_state(run_dir)
    required_stage = Stage.KIEM_DINH_ENGINE if final else Stage.KIEM_DINH_LOCAL
    if state.stage is not required_stage:
        raise MvpError(f"local audit requires {required_stage.value} stage")
    plan_path = episode / "Kich_ban" / "narration_plan.json"
    situations_path = episode / "Kich_ban" / "situations.json"
    semantic_path = episode / "Bao_cao" / "local_semantic_review.json"
    edl_path = episode / "Ke_hoach_canh" / "adaptive_edl.json"
    tts_path = episode / "TTS" / "situation_tts_manifest.json"
    source_anchors_path = run_dir / "local_evidence" / "source" / "anchors.json"
    program_dir = "program_final" if final else "program"
    program_anchors_path = run_dir / "local_evidence" / program_dir / "anchors.json"
    render_path = run_dir / ("final_render_result.json" if final else "proxy/render_result.json")

    plan = load_narration_plan(plan_path)
    situations = load_situations(situations_path)
    source_anchors = load_json(source_anchors_path, FrameAnchorDocument)
    program_anchors = load_json(program_anchors_path, FrameAnchorDocument)
    semantic = load_semantic_review(
        semantic_path,
        plan,
        source_anchors,
        program_anchors,
    )
    edl = load_json(edl_path, AdaptiveEdlDocument)
    tts = load_json(tts_path, SituationTtsManifest)
    render = load_json(render_path, RenderResult)
    report = build_local_audit(
        plan,
        situations,
        semantic,
        source_anchors,
        program_anchors,
        edl,
        tts,
        render,
        policy=_editorial_policy(episode),
    )
    report_name = "kiem_dinh_engine.json" if final else "kiem_dinh_local.json"
    dump_json(episode / "Bao_cao" / report_name, report)
    if not report.passed:
        errors = tuple(item for item in report.findings if item.severity == "ERROR")
        unit_to_situation = {unit.unit_id: unit.situation_id for unit in plan.units}
        situation_ids = tuple(
            dict.fromkeys(
                unit_to_situation[item.cue_id]
                for item in errors
                if item.cue_id in unit_to_situation
            )
        ) or tuple(dict.fromkeys(unit.situation_id for unit in plan.units))
        codes = tuple(dict.fromkeys(item.code for item in errors)) or ("AUDIT_NOT_PASSED",)
        fingerprint = content_fingerprint(
            (plan_path, situations_path, semantic_path, edl_path, tts_path)
        )
        record_local_repair(run_dir, situation_ids, codes, fingerprint)
        _write_next(
            run_dir,
            "Kiểm định cục bộ chặn "
            f"{', '.join(codes)}; sửa đúng tình huống {', '.join(situation_ids)}.",
        )
        return 1
    if final:
        publish_candidate(
            run_dir / "final_candidate.mp4",
            episode / "Thanh_pham" / "review_anime.mp4",
            episode / "Bao_cao" / "phien_ban_cu",
        )
        advance(
            run_dir,
            Stage.KIEM_DINH_ENGINE,
            Stage.HOAN_THANH,
            _engine_audit_passed=True,
        )
        _write_next(run_dir, "HOAN_THANH; giao review_anime.mp4 cho người dùng xem.")
        return 0
    advance(run_dir, Stage.KIEM_DINH_LOCAL, Stage.DUNG_VIDEO_CUOI)
    _write_next(run_dir, "Kiểm định proxy đạt; render --quality final.")
    return 0


def _prompt(run_dir: Path) -> int:
    _, episode = _episode(run_dir)
    root = episode.parents[3]
    job_path = run_dir / "cong_viec_antigravity.json"
    if not job_path.is_file():
        raise MvpError("run has no cong_viec_antigravity.json; run prepare first")
    output = run_dir / "PROMPT_GUI_ANTIGRAVITY.txt"
    if output.is_file() and output.read_text(encoding="utf-8").strip():
        print(output.resolve())
        return 0
    rendered = render_operator_prompt(
        run_dir,
        root / "Bo_nao_Antigravity" / "PROMPT_MOT_LAN_CHAY.md",
    )
    output.write_text(rendered, encoding="utf-8")
    print(output.resolve())
    return 0


def _gemini_profile_path(run_dir: Path) -> Path:
    _, episode = _episode(run_dir)
    return episode.parents[3] / ".local" / "gemini_ultra_profile.json"


def _web_verify_enroll(run_dir: Path, account_hint: str | None) -> int:
    if not account_hint:
        raise MvpError("gemini-web enroll requires --account-hint")
    print("Nhập email của tài khoản Gemini Ultra đang hiển thị trong profile Chrome:")
    email = sys.stdin.readline().strip()
    if not email:
        raise MvpError("gemini-web enroll requires the signed-in email on stdin")
    binding = GeminiUltraProfileBinding(account_sha256(email), account_hint)
    output = _gemini_profile_path(run_dir)
    write_profile_binding(output, binding)
    print(output.resolve())
    return 0


def _load_verified_critic(
    run_dir: Path, phase: str, storyboard: AtomicStoryboard
) -> CriticReviewDocument:
    phase_lower = phase.casefold()
    review_path = run_dir / "gemini_web" / phase_lower / f"critic_{phase_lower}.json"
    load_operator_verified_review(
        run_dir,
        phase_lower,
        CriticReviewDocument,
        ledger=_operator_ledger(run_dir),
    )
    expected_phase = "SCRIPT" if phase.upper() == "SCRIPT" else "VIDEO"
    return load_critic_review(
        review_path,
        storyboard,
        expected_phase,
    )


def _accept_operator_review(
    run_dir: Path,
    phase: str,
    operator_review: CriticReviewDocument | None = None,
) -> int:
    started = time.perf_counter()
    phase_upper = phase.upper()
    state, episode = _episode(run_dir)
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    truth = load_truth(
        episode / "Su_that" / "su_that_tap_phim.json",
        source_duration_ms=source.duration_ms,
    )
    shots = load_json(run_dir / "shots.json", ShotDocument)
    storyboard = load_atomic_storyboard(
        episode / "Kich_ban" / "atomic_storyboard.json",
        truth,
        shots.shots,
        source.duration_ms,
    )
    if phase_upper == "SCRIPT":
        if state.stage is not Stage.CHO_GEMINI_SCRIPT:
            raise MvpError("Gemini Web script accept requires CHO_GEMINI_SCRIPT stage")
        try:
            review = operator_review or _load_verified_critic(run_dir, "script", storyboard)
            source_anchors = load_json(
                run_dir / "atomic_evidence" / "source" / "anchors.json", FrameAnchorDocument
            )
            validate_critic_evidence(review, storyboard, source_anchors)
        except MvpError:
            mark_human_required(run_dir, "GEMINI_WEB_SCRIPT_VERIFY_FAILED")
            _write_next(run_dir, "Gemini Web script không hợp lệ; cần người xử lý.")
            raise
        failed = tuple(item for item in review.beat_reviews if item.finding_codes)
        if failed:
            repaired = record_beat_repair(
                run_dir,
                "SCRIPT",
                tuple(item.beat_id for item in failed),
                tuple(dict.fromkeys(code for item in failed for code in item.finding_codes)),
            )
            _write_next(
                run_dir,
                f"Gemini Ultra Web chặn {len(failed)} beat script; sửa rồi chạy resume, "
                f"vòng {len(repaired.repair_history)}/3.",
            )
            return 1
        record_stage_metric(run_dir, Stage.CHO_GEMINI_SCRIPT, _elapsed_ms(started), 0, 0, ())
        advance(run_dir, Stage.CHO_GEMINI_SCRIPT, Stage.PHAN_BIEN_KICH_BAN)
        advance(run_dir, Stage.PHAN_BIEN_KICH_BAN, Stage.TAO_TTS)
        _write_next(run_dir, "Gemini Ultra Web đã duyệt script; chạy tts.")
    elif phase_upper in {"PROXY", "FINAL"}:
        expected_stage = (
            Stage.CHO_GEMINI_PROXY if phase_upper == "PROXY" else Stage.CHO_GEMINI_FINAL
        )
        if state.stage is not expected_stage:
            raise MvpError(f"Gemini Web {phase.casefold()} accept stage does not match")
        try:
            review = operator_review or _load_verified_critic(
                run_dir, phase.casefold(), storyboard
            )
            source_anchors = load_json(
                run_dir / "atomic_evidence" / "source" / "anchors.json", FrameAnchorDocument
            )
            program_anchors = load_json(
                run_dir / "atomic_evidence" / "program" / "anchors.json", FrameAnchorDocument
            )
            validate_critic_evidence(review, storyboard, source_anchors, program_anchors)
        except MvpError:
            mark_human_required(run_dir, f"GEMINI_WEB_{phase_upper}_VERIFY_FAILED")
            _write_next(run_dir, f"Gemini Web {phase.casefold()} không hợp lệ; cần người xử lý.")
            raise
        failed = tuple(item for item in review.beat_reviews if item.finding_codes)
        if failed:
            repaired = record_beat_repair(
                run_dir,
                "VIDEO",
                tuple(item.beat_id for item in failed),
                tuple(dict.fromkeys(code for item in failed for code in item.finding_codes)),
            )
            _write_next(
                run_dir,
                f"Gemini Ultra Web chặn {len(failed)} beat; sửa rồi chạy resume, "
                f"vòng {len(repaired.repair_history)}/3.",
            )
            return 1
        if phase_upper == "PROXY":
            record_stage_metric(run_dir, Stage.CHO_GEMINI_PROXY, _elapsed_ms(started), 0, 0, ())
            advance(run_dir, Stage.CHO_GEMINI_PROXY, Stage.DUNG_VIDEO_CUOI)
            _write_next(run_dir, "Gemini Ultra Web đã duyệt proxy; render --quality final.")
        else:
            record_stage_metric(run_dir, Stage.CHO_GEMINI_FINAL, _elapsed_ms(started), 0, 0, ())
            advance(run_dir, Stage.CHO_GEMINI_FINAL, Stage.KIEM_DINH_ENGINE)
            _write_next(run_dir, "Gemini Ultra Web đã duyệt final; chạy audit --phase engine.")
    else:
        raise MvpError("Gemini Web phase is invalid")
    print((run_dir / "gemini_web" / phase.casefold() / f"critic_{phase.casefold()}.json").resolve())
    return 0


_BROWSER_HUMAN_CODES = {
    "LOGIN_REQUIRED": "CAN_DANG_NHAP_GEMINI_ULTRA",
    "ACCOUNT_MISMATCH": "SAI_TAI_KHOAN_GEMINI",
    "MODEL_NOT_FOUND": "KHONG_THAY_MODEL_3_7_FLASH",
    "UPLOAD_FAILED": "GEMINI_UPLOAD_THAT_BAI",
    "PROMPT_NOT_SENT": "GEMINI_GUI_PROMPT_THAT_BAI",
    "INVALID_RESPONSE": "GEMINI_RESPONSE_KHONG_HOP_LE",
    "INVALID_EVIDENCE": "BANG_CHUNG_BROWSER_KHONG_HOP_LE",
    "BROWSER_START_FAILED": "KHONG_MO_DUOC_CHROME_GEMINI",
}


def _operator_root(run_dir: Path) -> Path:
    return run_dir.resolve().parent.parent


def _operator_ledger(run_dir: Path) -> OperatorLedger:
    local = _operator_root(run_dir) / ".local"
    key = load_or_create_ledger_key(local / "gemini_operator.key")
    return OperatorLedger(local / "gemini_operator_ledger.jsonl", key)


def run_operator_phase(
    run_dir: Path,
    phase: str,
    *,
    prompt_override: Path | None = None,
    force_new_chat: bool = False,
) -> CriticReviewDocument:
    phase_upper = phase.upper()
    packet = build_browser_packet(run_dir, phase_upper)
    root = _operator_root(run_dir)
    binding = load_profile_binding(root / ".local" / "gemini_ultra_profile.json")
    registry = GeminiSessionRegistry(root / ".local" / "gemini_operator_session.json")
    ledger = _operator_ledger(run_dir)
    policy = OperatorPolicy.required()
    request = issue_request(
        run_dir.resolve().name,
        phase_upper,
        sha256_file(Path(packet.media_path)),
        packet.packet_sha256,
    )

    def browser_session(operator_request, browser_packet):
        def launch_fresh_session() -> tuple[ChromeLaunch, GeminiSessionMetadata]:
            fresh_launch = launch_managed_chrome(root)
            fresh_metadata = GeminiSessionMetadata(
                run_id=run_dir.resolve().name,
                chrome_pid=fresh_launch.chrome_pid,
                debugger_address=fresh_launch.debugger_address,
                conversation_url=None,
                started_at=datetime.now(UTC).isoformat(),
                phase_turns={},
            )
            registry.save(fresh_metadata)
            return fresh_launch, fresh_metadata

        metadata = registry.load()
        if metadata is None:
            launch, metadata = launch_fresh_session()
            print(
                "Gemini Chrome operator đã mở: "
                f"{(root / '.local' / 'gemini_ultra_chrome').resolve()}"
            )
            print(
                "Hãy đăng nhập đúng tài khoản Ultra và tự chọn "
                "3.7 Flash + Tư duy mở rộng trên cửa sổ này."
            )
        else:
            try:
                metadata = registry.assert_attachable(run_dir.resolve().name)
            except StaleGeminiSessionError:
                if not force_new_chat:
                    raise
                registry.clear(run_dir.resolve().name)
                launch, metadata = launch_fresh_session()
                print("Phiên Chrome cũ đã stale; đã mở lại operator bằng profile hiện có.")
            else:
                launch = connect_managed_chrome(metadata)
                print("Đã nối lại phiên Gemini Web đang mở của run này.")
            if force_new_chat and metadata.conversation_url is not None:
                metadata = registry.start_new_chat(
                    run_dir.resolve().name,
                    started_at=datetime.now(UTC).isoformat(),
                )
                print("Đã tách chat cũ; đang mở một Cuộc trò chuyện mới.")
        try:
            if prompt_override is None:
                prompt_path = Path(browser_packet.prompt_path)
                upload_paths = tuple(Path(path) for path in browser_packet.upload_paths)
            else:
                prompt_path = assert_inside_run(prompt_override, run_dir)
                upload_paths = ()
            prompt = prompt_path.read_text(encoding="utf-8")
            screenshot_path = (
                run_dir
                / "gemini_web"
                / phase_upper.casefold()
                / "screenshots"
                / "session.png"
            )
            checkpoint_path = (
                run_dir
                / "gemini_web"
                / phase_upper.casefold()
                / (
                    f"browser_result_{browser_packet.packet_sha256}_"
                    f"{sha256_file(prompt_path)}.json"
                )
            )
            if (
                not force_new_chat
                and metadata.conversation_url
                and screenshot_path.is_file()
                and not (run_dir / "gemini_web" / "session.json").is_file()
            ):
                result = capture_existing_gemini_response(
                    launch.page,
                    conversation_url=metadata.conversation_url,
                    account_hint=binding.account_hint,
                    expected_account_sha256=binding.account_sha256,
                    screenshot_path=screenshot_path,
                    chrome_pid=launch.chrome_pid,
                    started_at=metadata.started_at,
                )
                turn_number = metadata.phase_turns.get(phase_upper, 0)
                if turn_number <= 0:
                    raise MvpError("Gemini recovered response has no recorded turn")
                dump_json(checkpoint_path, result)
            else:
                expected_turn = registry.next_turn(
                    run_dir.resolve().name,
                    phase_upper,
                    max_turns=policy.max_turns,
                )
                submitted_turn: int | None = None

                def record_submitted_turn() -> None:
                    nonlocal submitted_turn
                    submitted_turn = registry.increment_turn(
                        run_dir.resolve().name,
                        phase_upper,
                        max_turns=policy.max_turns,
                    )
                    if submitted_turn != expected_turn:
                        raise MvpError("Gemini session turn count changed unexpectedly")

                result = run_gemini_session(
                    launch.page,
                    policy=policy,
                    account_hint=binding.account_hint,
                    expected_account_sha256=binding.account_sha256,
                    upload_paths=upload_paths,
                    prompt=prompt,
                    screenshot_path=screenshot_path,
                    chrome_pid=launch.chrome_pid,
                    conversation_url=metadata.conversation_url,
                    on_prompt_submitted=record_submitted_turn,
                )
                if submitted_turn is None:
                    raise MvpError("Gemini prompt submission was not recorded")
                turn_number = submitted_turn
                dump_json(checkpoint_path, result)
            registry.update_conversation(
                run_dir.resolve().name,
                result.observation.conversation_url,
            )
            (run_dir / "gemini_web" / "session.json").write_text(
                json.dumps(
                    {
                    "run_id": run_dir.resolve().name,
                    "conversation_url": result.observation.conversation_url,
                    "phase": phase_upper,
                    "turn_number": turn_number,
                    "phase_turns": registry.load().phase_turns,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            return result
        finally:
            launch.detach()

    operator = GeminiWebOperator(
        run_dir=run_dir,
        binding=binding,
        ledger=ledger,
        session_runner=browser_session,
        policy=policy,
        operator_build_sha256=calculate_policy_sha256(root),
    )
    operator.run(request, packet)
    return load_operator_verified_review(
        run_dir,
        phase_upper,
        CriticReviewDocument,
        ledger=ledger,
    )


_REPAIRABLE_CRITIC_ERRORS = (
    "Gemini response",
    "Gemini critic",
    "JSON ",
    "critic review",
    "critic contains",
    "critic verdict",
    "VIDEO critic requires a sync verdict",
    "SCRIPT critic sync verdict",
)


def _is_repairable_critic_error(error: MvpError) -> bool:
    message = str(error)
    return any(fragment in message for fragment in _REPAIRABLE_CRITIC_ERRORS)


def _validate_operator_review(
    run_dir: Path,
    phase: str,
    review: object,
) -> None:
    if not isinstance(review, CriticReviewDocument):
        return
    _, episode = _episode(run_dir)
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    truth = load_truth(
        episode / "Su_that" / "su_that_tap_phim.json",
        source_duration_ms=source.duration_ms,
    )
    shots = load_json(run_dir / "shots.json", ShotDocument)
    storyboard = load_atomic_storyboard(
        episode / "Kich_ban" / "atomic_storyboard.json",
        truth,
        shots.shots,
        source.duration_ms,
    )
    source_anchors = load_json(
        run_dir / "atomic_evidence" / "source" / "anchors.json",
        FrameAnchorDocument,
    )
    program_anchors = (
        load_json(
            run_dir / "atomic_evidence" / "program" / "anchors.json",
            FrameAnchorDocument,
        )
        if phase.upper() in {"PROXY", "FINAL"}
        else None
    )
    validate_critic_evidence(review, storyboard, source_anchors, program_anchors)


def _write_critic_repair_prompt(
    run_dir: Path,
    phase: str,
    error: MvpError,
    *,
    turn_number: int,
) -> Path:
    phase_upper = phase.upper()
    documents = [
        load_json(
            run_dir / "atomic_evidence" / "source" / "anchors.json",
            FrameAnchorDocument,
        )
    ]
    if phase_upper in {"PROXY", "FINAL"}:
        documents.append(
            load_json(
                run_dir / "atomic_evidence" / "program" / "anchors.json",
                FrameAnchorDocument,
            )
        )
    position_order = {"START": 0, "MIDDLE": 1, "END": 2}
    anchors_by_beat: dict[str, list[object]] = {}
    for document in documents:
        for anchor in document.anchors:
            anchors_by_beat.setdefault(anchor.span_id, []).append(anchor)
    requirements = {
        beat_id: [
            anchor.anchor_id
            for anchor in sorted(
                anchors,
                key=lambda item: (
                    0 if item.timeline == "SOURCE" else 1,
                    item.range_id,
                    position_order[item.position],
                ),
            )
        ]
        for beat_id, anchors in sorted(anchors_by_beat.items())
    }
    prompt = (
        "Phản hồi trước đã được nhận đầy đủ nhưng chưa qua validator. "
        f"Lỗi cần sửa: {error}. Trả lại DUY NHẤT toàn bộ JSON object hoàn chỉnh "
        "cho tất cả beat, không markdown và không giải thích ngoài JSON. Chỉ sửa các "
        "trường cần thiết để qua lỗi này; giữ nguyên các finding_codes và sync_verdict "
        "đã đánh giá từ hình ảnh thật, không được đổi lỗi thật thành MATCH. Giữ nguyên "
        "observed_visual, narration_summary và note trừ khi chúng sai schema. "
        "evidence_refs của từng beat phải chứa TOÀN BỘ anchor_id tương ứng trong bảng "
        "bắt buộc sau (có thể thêm anchor hợp lệ khác, không được bịa ID):\n"
        + json.dumps(requirements, ensure_ascii=False, sort_keys=True, indent=2)
    )
    output = (
        run_dir
        / "gemini_web"
        / phase_upper.casefold()
        / f"auto_repair_prompt_{turn_number:02d}.txt"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(prompt + "\n", encoding="utf-8")
    return output


def _run_operator_conversation(
    run_dir: Path,
    phase: str,
    *,
    force_new_chat: bool = False,
    initial_prompt: Path | None = None,
) -> CriticReviewDocument:
    prompt_override = initial_prompt
    max_turns = OperatorPolicy.required().max_turns
    for turn_number in range(1, max_turns + 1):
        try:
            if prompt_override is not None:
                review = run_operator_phase(
                    run_dir,
                    phase,
                    prompt_override=prompt_override,
                )
            elif force_new_chat:
                review = run_operator_phase(
                    run_dir,
                    phase,
                    force_new_chat=True,
                )
            else:
                review = run_operator_phase(run_dir, phase)
            _validate_operator_review(run_dir, phase, review)
            return review
        except GeminiBrowserError:
            raise
        except MvpError as exc:
            if not _is_repairable_critic_error(exc):
                raise
            if turn_number >= max_turns:
                raise MvpError(
                    f"Gemini critic remained invalid after {max_turns} turns: {exc}"
                ) from exc
            prompt_override = _write_critic_repair_prompt(
                run_dir,
                phase,
                exc,
                turn_number=turn_number + 1,
            )
    raise MvpError("Gemini critic repair loop ended unexpectedly")


def _gemini_web_run(
    run_dir: Path,
    phase: str,
    *,
    force_new_chat: bool = False,
) -> int:
    phase_upper = phase.upper()
    expected = {
        "SCRIPT": (Stage.VIET_LOI, Stage.CHO_GEMINI_SCRIPT),
        "PROXY": (Stage.PHAN_BIEN_VIDEO, Stage.CHO_GEMINI_PROXY),
        "FINAL": (Stage.CHO_GEMINI_FINAL, Stage.CHO_GEMINI_FINAL),
    }[phase_upper]
    state = read_state(run_dir)
    if state.stage is Stage.CAN_CON_NGUOI_XU_LY:
        state = resume_browser_review(run_dir, phase_upper)
    if state.stage is expected[0]:
        if expected[0] is not expected[1]:
            advance(run_dir, expected[0], expected[1])
    elif state.stage is not expected[1]:
        raise MvpError(f"Gemini Web {phase.casefold()} run stage does not match")
    try:
        review = _run_operator_conversation(
            run_dir,
            phase_upper,
            force_new_chat=force_new_chat,
        )
    except GeminiBrowserError as exc:
        code = _BROWSER_HUMAN_CODES.get(exc.code, "GEMINI_WEB_OPERATOR_THAT_BAI")
        mark_human_required(run_dir, code)
        show_command = (
            "uv run python run_episode.py gemini-web show "
            f'--run "{run_dir.resolve()}"'
        )
        _write_next(
            run_dir,
            f"Gemini Web dừng: {exc}. Giữ nguyên Chrome. Nếu cửa sổ không hiện, "
            f"chạy PowerShell: {show_command}. Sau khi đăng nhập/chọn model, chạy lại "
            f"gemini-web run --phase {phase.casefold()}.",
            code=code,
        )
        return 1
    except MvpError as exc:
        code = "BANG_CHUNG_BROWSER_KHONG_HOP_LE"
        mark_human_required(run_dir, code)
        _write_next(
            run_dir,
            f"Gemini Web từ chối bằng chứng: {exc}. Báo lại Codex để sửa operator.",
            code=code,
        )
        return 1
    result = _accept_operator_review(run_dir, phase_upper, review)
    if result == 0 and phase_upper == "FINAL":
        _gemini_web_stop(run_dir)
    return result


def _gemini_web_continue(run_dir: Path, phase: str, prompt_file: Path) -> int:
    phase_upper = phase.upper()
    prompt_path = assert_inside_run(prompt_file, run_dir)
    if not prompt_path.is_file():
        raise MvpError("Gemini follow-up prompt file is missing")
    state = read_state(run_dir)
    expected_stage = {
        "SCRIPT": Stage.CHO_GEMINI_SCRIPT,
        "PROXY": Stage.CHO_GEMINI_PROXY,
        "FINAL": Stage.CHO_GEMINI_FINAL,
    }.get(phase_upper)
    if expected_stage is None:
        raise MvpError("Gemini Web phase is invalid")
    if state.stage is Stage.CAN_CON_NGUOI_XU_LY:
        resume_browser_review(run_dir, phase_upper)
    elif state.stage is not expected_stage:
        raise MvpError("Gemini follow-up phase does not match the current stage")
    try:
        review = _run_operator_conversation(
            run_dir,
            phase_upper,
            initial_prompt=prompt_path,
        )
    except GeminiBrowserError as exc:
        code = _BROWSER_HUMAN_CODES.get(exc.code, "GEMINI_WEB_OPERATOR_THAT_BAI")
        mark_human_required(run_dir, code)
        _write_next(run_dir, f"Gemini follow-up dừng: {exc}", code=code)
        return 1
    except MvpError as exc:
        mark_human_required(run_dir, "BANG_CHUNG_BROWSER_KHONG_HOP_LE")
        _write_next(
            run_dir,
            f"Gemini follow-up bị từ chối: {exc}",
            code="BANG_CHUNG_BROWSER_KHONG_HOP_LE",
        )
        return 1
    return _accept_operator_review(run_dir, phase_upper, review)


def _gemini_web_stop(run_dir: Path) -> int:
    root = _operator_root(run_dir)
    registry = GeminiSessionRegistry(root / ".local" / "gemini_operator_session.json")
    metadata = registry.load()
    if metadata is None:
        print("Gemini Web không có phiên đang hoạt động.")
        return 0
    if metadata.run_id != run_dir.resolve().name:
        raise MvpError("Gemini session belongs to another run")
    try:
        launch = connect_managed_chrome(metadata)
    except GeminiBrowserError:
        registry.clear(run_dir.resolve().name)
        print("Gemini Web session đã stale; đã dọn metadata.")
        return 0
    try:
        launch.close()
    finally:
        registry.clear(run_dir.resolve().name)
    print("Gemini Web session đã đóng và metadata đã dọn.")
    return 0


def _gemini_web_show(run_dir: Path) -> int:
    root = _operator_root(run_dir)
    registry = GeminiSessionRegistry(root / ".local" / "gemini_operator_session.json")
    run_id = run_dir.resolve().name
    metadata = registry.load()
    if metadata is None:
        launch = launch_managed_chrome(root)
        registry.save(
            GeminiSessionMetadata(
                run_id=run_id,
                chrome_pid=launch.chrome_pid,
                debugger_address=launch.debugger_address,
                conversation_url=None,
                started_at=datetime.now(UTC).isoformat(),
                phase_turns={},
            )
        )
    else:
        metadata = registry.assert_attachable(run_id)
        ensure_managed_chrome_visible(root, metadata)
        launch = connect_managed_chrome(metadata)
    try:
        launch.page.show()
    finally:
        launch.detach()
    print("Cửa sổ Gemini Chrome operator đã được khôi phục và đưa ra màn hình.")
    return 0


def _gemini_web_smoke(run_dir: Path) -> int:
    root = _operator_root(run_dir)
    binding = load_profile_binding(root / ".local" / "gemini_ultra_profile.json")
    policy = OperatorPolicy.required()
    smoke_dir = run_dir / "gemini_web" / "smoke"
    evidence = smoke_dir / "operator-smoke.txt"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("GEMINI WEB OPERATOR SMOKE TEST\n", encoding="utf-8")
    launch = launch_managed_chrome(root)
    try:
        observation, response = run_gemini_session(
            launch.page,
            policy=policy,
            account_hint=binding.account_hint,
            expected_account_sha256=binding.account_sha256,
            upload_paths=(evidence,),
            prompt="Trả lời đúng chuỗi GEMINI_WEB_OPERATOR_OK, không thêm nội dung khác.",
            screenshot_path=smoke_dir / "session.png",
            chrome_pid=launch.chrome_pid,
        )
    finally:
        launch.close()
    if response.strip() != "GEMINI_WEB_OPERATOR_OK":
        raise GeminiBrowserError(
            "INVALID_RESPONSE", "Gemini smoke response is not the required exact string"
        )
    print(observation.conversation_url)
    return 0


def _gemini_web(args: argparse.Namespace) -> int:
    if args.action not in {"enroll", "stop", "show"}:
        state = read_state(args.run)
        episode = Path(state.episode_dir) if state.episode_dir else None
        if episode is not None and (
            episode / "Kich_ban" / "narration_plan.json"
        ).is_file():
            raise MvpError(
                "gemini-web is optional for legacy runs only; local situation runs "
                "use audit --phase local|engine"
            )
    if args.action == "enroll":
        return _web_verify_enroll(args.run, args.account_hint)
    if args.action == "smoke":
        try:
            return _gemini_web_smoke(args.run)
        except GeminiBrowserError as exc:
            code = _BROWSER_HUMAN_CODES.get(exc.code, "GEMINI_WEB_OPERATOR_THAT_BAI")
            mark_human_required(args.run, code)
            _write_next(args.run, f"Gemini Web smoke dừng: {exc}", code=code)
            return 1
    if args.action == "stop":
        return _gemini_web_stop(args.run)
    if args.action == "show":
        return _gemini_web_show(args.run)
    if args.action == "continue":
        if args.phase is None or args.prompt_file is None:
            raise MvpError("gemini-web continue requires --phase and --prompt-file")
        return _gemini_web_continue(args.run, args.phase, args.prompt_file)
    if args.phase is None:
        raise MvpError("gemini-web run requires --phase")
    return _gemini_web_run(
        args.run,
        args.phase,
        force_new_chat=args.action == "new-chat",
    )


def _audit_proxy_v2(run_dir: Path, episode: Path) -> int:
    state = read_state(run_dir)
    if state.stage is not Stage.KIEM_DINH_PROXY:
        raise MvpError("proxy audit requires KIEM_DINH_PROXY stage")
    plan = load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
    situations = load_situations(episode / "Su_that" / "situations.json")
    timeline = load_json(run_dir / "semantic_timeline.json", SemanticTimeline)
    tts = load_json(run_dir / "cue_tts_manifest.json", CueTtsManifest)
    edl = load_json(run_dir / "adaptive_edl.json", AdaptiveEdlDocument)
    render = load_json(run_dir / "proxy" / "render_result.json", RenderResult)
    context_path = run_dir / "story_context.json"
    context = (
        load_json(context_path, StoryContext)
        if context_path.is_file()
        else StoryContext((), (), (), "")
    )
    provenance = load_editor_ledger(run_dir / "editor_ledger.jsonl")
    report = build_v2_local_audit(
        plan, situations, timeline, tts, edl, render, provenance, context
    )
    dump_json(run_dir / "proxy" / "v2_audit.json", report)
    if not report.passed:
        codes = tuple(dict.fromkeys(item.code for item in report.findings))
        situation_ids = tuple(item.situation_id for item in situations.situations)
        fingerprint = content_fingerprint(
            (
                episode / "Kich_ban" / "narration_plan.json",
                episode / "Su_that" / "situations.json",
                run_dir / "semantic_timeline.json",
            )
        )
        route_editor_repair(run_dir, situation_ids, codes, fingerprint)
        _write_next(run_dir, f"Antigravity sửa lỗi proxy: {', '.join(codes)}.")
        return 1
    advance(run_dir, Stage.KIEM_DINH_PROXY, Stage.CHO_NGUOI_DUNG_DUYET_PROXY)
    _write_next(
        run_dir,
        "Proxy đã đạt kiểm định. Hãy xem video rồi chọn đúng một lệnh: "
        f"approve-proxy --run \"{run_dir}\" hoặc reject-proxy --run \"{run_dir}\" "
        "--note \"mô tả lỗi\" --situation situation-XXX. Hệ thống không tự duyệt.",
    )
    return 0


def _audit_situation_v2(run_dir: Path, episode: Path) -> int:
    state = read_state(run_dir)
    if state.stage is Stage.KIEM_DINH_TINH_HUONG:
        source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
        shots = load_json(run_dir / "shots.json", ShotDocument)
        situations = load_situations(episode / "Su_that" / "situations.json")
        plan = load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
        validate_situations(
            situations, None, shots.shots, source_duration_ms=source.duration_ms
        )
        validate_narration_plan(
            plan,
            situations,
            None,
            shots.shots,
            _editorial_policy(episode),
            source.duration_ms,
            require_bridges=False,
        )
        advance(
            run_dir,
            Stage.KIEM_DINH_TINH_HUONG,
            Stage.TAO_TTS_TINH_HUONG,
        )
        _write_next(run_dir, "Tình huống hợp lệ; chạy tts --situation hiện tại.")
        return 0
    if state.stage is Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG:
        situations = load_situations(episode / "Su_that" / "situations.json")
        plan = load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
        context_path = run_dir / "story_context.json"
        context = (
            load_json(context_path, StoryContext)
            if context_path.is_file()
            else StoryContext((), (), (), "")
        )
        report = build_episode_coherence_audit(plan, situations, context)
        if not report.passed:
            codes = tuple(dict.fromkeys(item.code for item in report.findings))
            route_editor_repair(
                run_dir,
                (state.current_situation_id,),
                codes,
                content_fingerprint(
                    (
                        episode / "Kich_ban" / "narration_plan.json",
                        run_dir / "semantic_timeline.json",
                    )
                ),
            )
            return 1
        advance(
            run_dir,
            Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG,
            Stage.CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG,
        )
        _write_next(run_dir, "Timing đạt; chạy verifier-task --kind situation để kiểm tra từng cue.")
        return 0
    raise MvpError("situation audit stage is invalid")


def _audit_episode_v2(run_dir: Path, episode: Path) -> int:
    state = read_state(run_dir)
    if state.stage is not Stage.KIEM_DINH_MACH_TRUYEN_TOAN_TAP:
        raise MvpError("episode audit requires KIEM_DINH_MACH_TRUYEN_TOAN_TAP stage")
    report = build_episode_coherence_audit(
        load_narration_plan(episode / "Kich_ban" / "narration_plan.json"),
        load_situations(episode / "Su_that" / "situations.json"),
        StoryContext((), (), (), ""),
    )
    dump_json(run_dir / "episode_coherence_audit.json", report)
    if not report.passed:
        raise MvpError("episode coherence audit did not pass")
    advance(run_dir, Stage.KIEM_DINH_MACH_TRUYEN_TOAN_TAP, Stage.DUNG_PROXY)
    _write_next(run_dir, "Mạch toàn tập đạt; chạy render --quality proxy.")
    return 0


def _audit_engine_v2(run_dir: Path, episode: Path) -> int:
    state = read_state(run_dir)
    if state.stage is not Stage.KIEM_DINH_ENGINE:
        raise MvpError("v2 engine audit requires KIEM_DINH_ENGINE stage")
    require_approved_artifacts(run_dir)
    plan = load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
    situations = load_situations(episode / "Su_that" / "situations.json")
    timeline = load_json(run_dir / "semantic_timeline.json", SemanticTimeline)
    tts = load_json(run_dir / "cue_tts_manifest.json", CueTtsManifest)
    edl = load_json(run_dir / "adaptive_edl.json", AdaptiveEdlDocument)
    render = load_json(run_dir / "final_render_result.json", RenderResult)
    report = build_v2_local_audit(
        plan,
        situations,
        timeline,
        tts,
        edl,
        render,
        load_editor_ledger(run_dir / "editor_ledger.jsonl"),
        StoryContext((), (), (), ""),
    )
    dump_json(episode / "Bao_cao" / "kiem_dinh_engine_v2.json", report)
    if not report.passed:
        raise MvpError("v2 engine audit did not pass")
    require_approved_artifacts(run_dir)
    publish_candidate(
        run_dir / "final_candidate.mp4",
        episode / "Thanh_pham" / "review_anime.mp4",
        episode / "Bao_cao" / "phien_ban_cu",
    )
    advance(
        run_dir,
        Stage.KIEM_DINH_ENGINE,
        Stage.HOAN_THANH,
        _engine_audit_passed=True,
    )
    _write_next(run_dir, "HOAN_THANH; review_anime.mp4 đã qua approval và engine audit.")
    return 0


def _audit(run_dir: Path, phase: str, codex_review: Path | None) -> int:
    _, episode = _episode(run_dir)
    if phase == "script":
        return _audit_script(run_dir, episode)
    if phase == "local":
        return _audit_local(run_dir, episode)
    if phase == "situation":
        return _audit_situation_v2(run_dir, episode)
    if phase == "episode":
        return _audit_episode_v2(run_dir, episode)
    if phase == "proxy" and read_state(run_dir).editorial_revision >= 1:
        return _audit_proxy_v2(run_dir, episode)
    if phase == "engine":
        if read_state(run_dir).editorial_revision >= 1:
            return _audit_engine_v2(run_dir, episode)
        if (episode / "Kich_ban" / "narration_plan.json").is_file():
            return _audit_local(run_dir, episode, final=True)
        return _audit_atomic_engine(run_dir, episode)
    return _audit_video(run_dir, episode, codex_review)


def _resume(run_dir: Path, phase: str) -> int:
    state, episode = _episode(run_dir)
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    truth = load_truth(
        episode / "Su_that" / "su_that_tap_phim.json",
        source_duration_ms=source.duration_ms,
    )
    shots = load_json(run_dir / "shots.json", ShotDocument)
    load_atomic_storyboard(
        episode / "Kich_ban" / "atomic_storyboard.json",
        truth,
        shots.shots,
        source.duration_ms,
    )
    resumed = resume_beat_repair(run_dir, phase.upper())
    instruction = (
        "Tạo lại critic_script.json bằng critic context mới."
        if resumed.stage is Stage.VIET_LOI
        else "Chạy tts; cache sẽ chỉ tạo lại beat đã đổi."
    )
    _write_next(run_dir, instruction)
    return 0


def _editorial_approval_paths(run_dir: Path) -> tuple[Path, ...]:
    paths = [
        path
        for path in sorted((run_dir / "accepted_editorial").rglob("*.json"))
        if path.is_file()
    ]
    paths.extend(
        path
        for path in (
            run_dir / "semantic_timeline.json",
            run_dir / "cue_tts_manifest.json",
            run_dir / "adaptive_edl.json",
        )
        if path.is_file()
    )
    if not paths:
        raise MvpError("proxy approval requires accepted editorial artifacts")
    return tuple(paths)


def _approve_proxy_command(run_dir: Path) -> int:
    proxy = run_dir / "proxy" / "review_proxy.mp4"
    approve_proxy(run_dir, proxy, _editorial_approval_paths(run_dir))
    print(run_dir / "proxy_approval.json")
    return 0


def _reject_proxy_command(
    run_dir: Path, note: str, situation_ids: tuple[str, ...]
) -> int:
    reject_proxy(run_dir, note, situation_ids)
    _write_next(
        run_dir,
        "Antigravity sửa đúng tình huống bị từ chối rồi nộp revision mới.",
        code="USER_REJECTED_PROXY",
    )
    return 0


def _frame_refs(run_dir: Path) -> tuple[str, ...]:
    path = run_dir / "frame_manifest.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        frames = raw["frames"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MvpError(f"cannot load frame manifest: {path}") from exc
    if not isinstance(frames, list) or not frames or not all(
        isinstance(item, str) and item.strip() for item in frames
    ):
        raise MvpError("frame manifest requires non-empty frame paths")
    return tuple(frames)


def _structure_task_command(run_dir: Path) -> int:
    state, episode = _episode(run_dir)
    if state.stage is not Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG:
        raise MvpError("structure-task requires CHO_ANTIGRAVITY_CHIA_TINH_HUONG stage")
    input_paths = (
        run_dir / "transcript_english.json",
        run_dir / "shots.json",
        run_dir / "frame_manifest.json",
    )
    revision = max(1, state.editorial_revision)
    task = create_structure_task(run_dir, run_dir.name, revision, input_paths)
    packet = build_structure_editor_packet(
        load_json(episode / "Dau_vao" / "source_ref.json", SourceRef),
        load_json(input_paths[0], TranscriptDocument),
        load_json(input_paths[1], ShotDocument),
        input_paths[2],
        task=task,
    )
    begin_structure_task(run_dir, task.task_id, task.revision)
    output = run_dir / "cong_viec_antigravity.json"
    dump_json(output, packet)
    prompt = run_dir / "PROMPT_GUI_ANTIGRAVITY.txt"
    prompt.write_text(render_structure_editor_prompt(packet), encoding="utf-8")
    staging = run_dir / "editor_staging" / task.task_id
    _write_next(
        run_dir,
        "Antigravity chỉ chia cấu trúc tập và ghi situation_index_draft.json vào "
        f'editor_staging/{task.task_id}. Sau đó chạy: accept-situation-index --run '
        f'"{run_dir}" --task {task.task_id} --input "{staging}".',
    )
    print(output)
    return 0


def _accept_situation_index_command(
    run_dir: Path, task_id: str, staging_dir: Path
) -> int:
    state, episode = _episode(run_dir)
    if state.stage is not Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG:
        raise MvpError("accept-situation-index requires the structure wait stage")
    if state.editor_task_id != task_id:
        raise MvpError("structure task does not match the active task")
    accepted = accept_antigravity_structure_submission(run_dir, task_id, staging_dir)
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    transcript = load_json(run_dir / "transcript_english.json", TranscriptDocument)
    shots = load_json(run_dir / "shots.json", ShotDocument)
    index = load_situation_index(
        Path(accepted.accepted_path), source, transcript, shots, _frame_refs(run_dir)
    )
    next_entry = next_editable_situation(index, ())
    if next_entry is None:
        raise MvpError("accepted situation index has no editable situation")
    canonical = run_dir / "situation_index.json"
    shutil.copy2(accepted.accepted_path, canonical)
    if sha256_file(canonical) != accepted.index_sha256:
        raise MvpError("accepted situation index copy verification failed")
    advance(
        run_dir,
        Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG,
        Stage.KIEM_DINH_CHI_MUC_TINH_HUONG,
    )
    accept_structure_index(run_dir, accepted.index_sha256, next_entry.situation_id)
    _write_next(
        run_dir,
        f"Chỉ mục hợp lệ; chạy editor-task cho {next_entry.situation_id}.",
    )
    print(canonical)
    return 0


def _editor_task_command(run_dir: Path) -> int:
    state, episode = _episode(run_dir)
    if state.stage is not Stage.CHO_ANTIGRAVITY_TINH_HUONG:
        raise MvpError("editor-task requires CHO_ANTIGRAVITY_TINH_HUONG stage")
    if not state.current_situation_id:
        raise MvpError("editor-task requires a current situation ID")
    index_path = run_dir / "situation_index.json"
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    transcript = load_json(run_dir / "transcript_english.json", TranscriptDocument)
    shots = load_json(run_dir / "shots.json", ShotDocument)
    index = load_situation_index(
        index_path, source, transcript, shots, _frame_refs(run_dir)
    )
    entry = next_editable_situation(index, state.locked_situation_ids)
    if entry is None or entry.situation_id != state.current_situation_id:
        raise MvpError("active situation does not match the accepted index order")
    if sha256_file(index_path) != state.accepted_situation_index_sha256:
        raise MvpError("accepted situation index hash changed")
    scope = materialize_situation_scope(
        run_dir,
        entry,
        transcript,
        shots,
        _frame_refs(run_dir),
        accepted_index_sha256=state.accepted_situation_index_sha256,
    )
    input_paths = tuple(Path(path) for path in scope.input_paths)
    task = create_editor_task(
        run_dir,
        run_dir.name,
        state.current_situation_id,
        max(1, state.editorial_revision),
        input_paths,
    )
    begin_editor_task(
        run_dir, task.task_id, task.situation_id, task.revision
    )
    context_path = run_dir / "story_context.json"
    context = (
        load_json(context_path, StoryContext)
        if context_path.is_file()
        else StoryContext((), (), (), "")
    )
    packet = build_scoped_situation_editor_packet(
        source,
        scope,
        _editorial_policy(episode),
        context,
        task=task,
    )
    output = run_dir / "cong_viec_antigravity.json"
    dump_json(output, packet)
    prompt_output = run_dir / "PROMPT_GUI_ANTIGRAVITY.txt"
    prompt_output.write_text(render_situation_editor_prompt(packet), encoding="utf-8")
    staging_dir = run_dir / "editor_staging" / task.task_id
    _write_next(
        run_dir,
        f"Antigravity xử lý {task.situation_id}; chỉ ghi hai draft vào "
        f"editor_staging/{task.task_id}. Sau đó chạy: accept-antigravity --run "
        f'"{run_dir}" --task {task.task_id} --input "{staging_dir}".',
    )
    print(output)
    return 0


def _accept_antigravity_command(
    run_dir: Path, task_id: str, staging_dir: Path
) -> int:
    state, episode = _episode(run_dir)
    task = load_editor_task(run_dir / "editor_tasks" / f"{task_id}.json")
    scope_path = next(
        (Path(path) for path in task.input_paths if path.endswith("scope.json")), None
    )
    if scope_path is None:
        raise MvpError("editor task is not scoped to an accepted situation")
    scope = load_situation_scope(scope_path, verify_files=True)
    if scope.accepted_index_sha256 != state.accepted_situation_index_sha256:
        raise MvpError("editor task uses a stale situation index")
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    full_transcript = load_json(run_dir / "transcript_english.json", TranscriptDocument)
    full_shots = load_json(run_dir / "shots.json", ShotDocument)
    index = load_situation_index(
        run_dir / "situation_index.json",
        source,
        full_transcript,
        full_shots,
        _frame_refs(run_dir),
    )
    entry = next(
        (item for item in index.situations if item.situation_id == task.situation_id),
        None,
    )
    if entry is None:
        raise MvpError("editor task situation is absent from the accepted index")
    staged_situation = load_json(staging_dir / "situation_draft.json", SituationDocument)
    staged_narration = load_json(staging_dir / "narration_draft.json", NarrationPlan)
    validate_submission_scope(entry, staged_situation, staged_narration)
    accepted = accept_antigravity_submission(run_dir, task_id, staging_dir)
    situation_draft = staged_situation
    narration_draft = staged_narration
    if (
        len(situation_draft.situations) != 1
        or situation_draft.situations[0].situation_id != accepted.situation_id
        or any(
            unit.situation_id != accepted.situation_id
            for unit in narration_draft.units
        )
    ):
        raise MvpError("Antigravity submission must contain exactly the active situation")
    situations_path = episode / "Su_that" / "situations.json"
    plan_path = episode / "Kich_ban" / "narration_plan.json"
    unfiltered_situations = (
        load_situations(situations_path).situations if situations_path.is_file() else ()
    )
    prior_plan = load_narration_plan(plan_path) if plan_path.is_file() else None
    prior_situations, prior_units, prior_claims = _filter_current_revision_artifacts(
        unfiltered_situations,
        prior_plan,
        {item.situation_id for item in index.situations if not item.excluded},
        run_dir / "accepted_editorial",
    )
    merged_situations = tuple(
        item for item in prior_situations if item.situation_id != accepted.situation_id
    ) + situation_draft.situations
    merged_situations = tuple(
        sorted(merged_situations, key=lambda item: item.source_start_ms)
    )
    kept_units = tuple(
        unit
        for unit in prior_units
        if unit.situation_id != accepted.situation_id
    )
    merged_units = (*kept_units, *narration_draft.units)
    used_claim_ids = {
        claim_id for unit in merged_units for cue in unit.cues for claim_id in cue.claim_ids
    }
    claim_by_id = {
        claim.claim_id: claim
        for claim in (
            *prior_claims,
            *narration_draft.claims,
        )
        if claim.claim_id in used_claim_ids
    }
    dump_json(
        situations_path,
        SituationDocument("LOCAL_EDITOR", "situation-v2", merged_situations),
    )
    dump_json(
        plan_path,
        NarrationPlan(
            "LOCAL_EDITOR", "situation-v2", merged_units, tuple(claim_by_id.values())
        ),
    )
    accept_editor_revision(run_dir, task_id, accepted.revision)
    _write_next(
        run_dir,
        f"Draft {accepted.situation_id} đã nhận; chạy audit --phase situation.",
    )
    print(
        run_dir
        / "accepted_editorial"
        / accepted.situation_id
        / f"revision-{accepted.revision:03d}"
    )
    return 0


def _timeline_command(run_dir: Path, situation_id: str | None) -> int:
    del situation_id
    state, episode = _episode(run_dir)
    if state.stage is not Stage.LAP_TIMELINE_TINH_HUONG:
        raise MvpError("timeline requires LAP_TIMELINE_TINH_HUONG stage")
    plan = load_narration_plan(episode / "Kich_ban" / "narration_plan.json")
    tts = load_json(run_dir / "cue_tts_manifest.json", CueTtsManifest)
    source = load_json(episode / "Dau_vao" / "source_ref.json", SourceRef)
    edl, timeline = build_semantic_timeline(
        plan, tts, source.duration_ms, EditorialPolicy()
    )
    dump_json(run_dir / "adaptive_edl.json", edl)
    dump_json(run_dir / "semantic_timeline.json", timeline)
    render_cue_audio_timeline(tts, timeline, run_dir / "aligned_narration.wav")
    advance(
        run_dir,
        Stage.LAP_TIMELINE_TINH_HUONG,
        Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG,
    )
    print(run_dir / "semantic_timeline.json")
    return 0


def _migrate_run(run_dir: Path, reason: str) -> int:
    state, episode = _episode(run_dir)
    if reason == "autonomous-operator":
        # Migration is metadata-only: accepted ledgers and artifacts remain untouched.
        if state.stage is Stage.CHO_NGUOI_DUNG_DUYET_PROXY:
            _write_next(run_dir, "Proxy sẵn sàng; chờ người dùng duyệt.")
        else:
            _write_next(run_dir, "Chạy operator để tiếp tục luồng tự động.")
        return _operator_command(run_dir)
    if reason == "require-situation-index":
        prior_task_id = state.editor_task_id
        archived_task_path = _archive_pre_index_revision(
            run_dir, episode, prior_task_id
        )
        migrate_to_structure_index(run_dir)
        if prior_task_id:
            superseded = run_dir / "superseded_tasks" / f"{prior_task_id}.json"
            superseded.parent.mkdir(parents=True, exist_ok=True)
            superseded.write_text(
                json.dumps(
                    {
                        "task_id": prior_task_id,
                        "reason": "WHOLE_EPISODE_INPUT_NOT_SCOPED",
                        "preserved_task_path": str(archived_task_path or ""),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return _structure_task_command(run_dir)
    if reason != "user-rejected":
        raise MvpError("unsupported migration reason")
    if state.stage is not Stage.HOAN_THANH:
        raise MvpError("migrate-run only accepts a completed run")
    revision_root = run_dir / "revisions" / "revision-001"
    candidates = (
        run_dir / "proxy",
        run_dir / "final_candidate.mp4",
        run_dir / "final_render_result.json",
        episode / "Kich_ban" / "narration_plan.json",
        episode / "Ke_hoach_canh" / "adaptive_edl.json",
        episode / "TTS" / "situation_tts_manifest.json",
        episode / "Thanh_pham" / "review_anime.mp4",
    )
    copied = 0
    for source in candidates:
        if not source.exists():
            continue
        bucket = "run" if source.is_relative_to(run_dir) else "episode"
        relative = source.relative_to(run_dir if bucket == "run" else episode)
        destination = revision_root / bucket / relative
        if source.is_dir():
            shutil.copytree(source, destination, dirs_exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if source.read_bytes() != destination.read_bytes():
                raise MvpError(f"migration copy verification failed: {source}")
        copied += 1
    if not copied:
        raise MvpError("completed run has no revision artifacts to preserve")
    migrate_rejected_run(run_dir, 2)
    _write_next(run_dir, "Chạy editor-task để Antigravity tạo revision 2.")
    print(revision_root)
    return 0


def _filter_current_revision_artifacts(
    prior_situations: tuple[Situation, ...],
    prior_plan: NarrationPlan | None,
    valid_situation_ids: set[str],
    accepted_root: Path,
) -> tuple[
    tuple[Situation, ...], tuple[NarrationUnit, ...], tuple[NarrationClaim, ...]
]:
    accepted_ids = {
        situation_id
        for situation_id in valid_situation_ids
        if (accepted_root / situation_id).is_dir()
    }
    situations = tuple(
        item for item in prior_situations if item.situation_id in accepted_ids
    )
    units = tuple(
        unit
        for unit in (() if prior_plan is None else prior_plan.units)
        if unit.situation_id in accepted_ids
    )
    used_claim_ids = {
        claim_id for unit in units for cue in unit.cues for claim_id in cue.claim_ids
    }
    claims = tuple(
        claim
        for claim in (() if prior_plan is None else prior_plan.claims)
        if claim.claim_id in used_claim_ids
    )
    return situations, units, claims


def _archive_pre_index_revision(
    run_dir: Path, episode: Path, prior_task_id: str
) -> Path | None:
    """Move generated pre-index outputs aside so a new revision starts clean."""
    run_root = run_dir.resolve()
    episode_root = episode.resolve()
    archive = run_root / "revisions" / "revision-001" / "legacy_active"

    def move(source: Path, base: Path, bucket: str) -> Path | None:
        if not source.exists():
            return None
        resolved = source.resolve()
        base_resolved = base.resolve()
        if not resolved.is_relative_to(base_resolved):
            raise MvpError(f"refusing to archive path outside expected root: {resolved}")
        destination = archive / bucket / resolved.relative_to(base_resolved)
        if destination.exists():
            raise MvpError(f"revision archive destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(resolved), str(destination))
        return destination

    for directory_name in ("Su_that", "Kich_ban", "TTS", "Thanh_pham", "Bao_cao"):
        directory = episode_root / directory_name
        if directory.is_dir():
            for child in tuple(directory.iterdir()):
                move(child, episode_root, "episode")
    plan_dir = episode_root / "Ke_hoach_canh"
    if plan_dir.is_dir():
        for child in tuple(plan_dir.iterdir()):
            move(child, episode_root, "episode")

    run_outputs = (
        "proxy",
        "local_evidence",
        "final_visual_audit",
        "title_audit",
        "crv_proxy_audit",
        "crv_final_sync_audit",
        "crv_final_sync_audio",
        "final_candidate.mp4",
        "final_render_result.json",
        "adaptive_edl.json",
        "semantic_timeline.json",
        "aligned_narration.wav",
        "cue_tts_manifest.json",
    )
    for name in run_outputs:
        move(run_root / name, run_root, "run")

    archived_task = None
    if prior_task_id:
        archived_task = move(
            run_root / "editor_tasks" / f"{prior_task_id}.json", run_root, "task"
        )
        move(run_root / "editor_staging" / prior_task_id, run_root, "task_staging")
    return archived_task


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "start":
            return _start(args)
        if args.command == "prepare":
            return _prepare(args.run)
        if args.command == "prompt":
            return _prompt(args.run)
        if args.command == "validate":
            return _validate(args.run, args.artifact)
        if args.command == "lock":
            return _lock(args.run)
        if args.command == "tts":
            return _tts(args.run, args.situation)
        if args.command == "render":
            return _render(args.run, args.quality)
        if args.command == "resume":
            return _resume(args.run, args.phase)
        if args.command == "audit":
            return _audit(args.run, args.phase, args.codex_review)
        if args.command == "gemini-web":
            return _gemini_web(args)
        if args.command == "migrate-run":
            return _migrate_run(args.run, args.reason)
        if args.command == "editor-task":
            return _editor_task_command(args.run)
        if args.command == "structure-task":
            return _structure_task_command(args.run)
        if args.command == "accept-situation-index":
            return _accept_situation_index_command(args.run, args.task, args.input)
        if args.command == "accept-antigravity":
            return _accept_antigravity_command(args.run, args.task, args.input)
        if args.command == "timeline":
            return _timeline_command(args.run, args.situation)
        if args.command == "approve-proxy":
            return _approve_proxy_command(args.run)
        if args.command == "reject-proxy":
            return _reject_proxy_command(args.run, args.note, tuple(args.situation))
        if args.command == "operator":
            return _operator_command(args.run)
        if args.command == "verifier-task":
            return _verifier_task_command(args.run, args.kind)
        if args.command == "accept-verifier":
            return _accept_verifier_command(args.run, args.task, args.input)
    except MvpError as exc:
        parser.error(str(exc))
    return 2
