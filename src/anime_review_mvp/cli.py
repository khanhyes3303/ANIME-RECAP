from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from .antigravity import (
    build_operator_job,
    calculate_policy_sha256,
    load_audit,
    load_scene_packets,
    load_script,
    load_truth,
    render_operator_prompt,
)
from .atomic import load_atomic_storyboard, load_critic_review, validate_critic_evidence
from .audit import build_atomic_engine_audit, build_engine_audit
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
    GeminiBrowserError,
    connect_managed_chrome,
    launch_managed_chrome,
    run_gemini_session,
)
from .gemini_session import GeminiSessionMetadata, GeminiSessionRegistry
from .gemini_web import (
    GeminiUltraProfileBinding,
    account_sha256,
    load_operator_verified_review,
    load_profile_binding,
    sha256_file,
    write_profile_binding,
)
from .jsonio import dump_json, load_json
from .media import (
    detect_shots,
    extract_atomic_source_anchors,
    extract_inspection_assets,
    extract_program_anchors,
    extract_span_anchors,
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
from .render import RenderResult, render_review
from .tts import synthesize_atomic_beats, synthesize_spans
from .validation import (
    narration_style_findings,
    validate_scene_packets,
    validate_script,
    validate_truth,
)
from .workflow import (
    Stage,
    advance,
    mark_human_required,
    new_state,
    read_state,
    record_beat_repair,
    record_repair,
    record_stage_metric,
    resume_beat_repair,
    resume_browser_review,
)
from .workspace import assert_inside_run, create_job, publish_candidate


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
        ),
    )
    lock = subparsers.add_parser("lock")
    lock.add_argument("--run", required=True, type=Path)
    tts = subparsers.add_parser("tts")
    tts.add_argument("--run", required=True, type=Path)
    render = subparsers.add_parser("render")
    render.add_argument("--run", required=True, type=Path)
    render.add_argument("--quality", choices=("proxy", "final"), default="final")
    resume = subparsers.add_parser("resume")
    resume.add_argument("--run", required=True, type=Path)
    resume.add_argument("--phase", required=True, choices=("script", "tts", "video"))
    audit = subparsers.add_parser("audit")
    audit.add_argument("--run", required=True, type=Path)
    audit.add_argument("--phase", required=True, choices=("script", "video", "engine"))
    audit.add_argument("--codex-review", type=Path)
    gemini_web = subparsers.add_parser(
        "gemini-web", help="Vận hành Gemini Ultra Web bằng Chrome do engine sở hữu"
    )
    gemini_web.add_argument(
        "action", choices=("enroll", "smoke", "run", "continue", "stop")
    )
    gemini_web.add_argument("--run", required=True, type=Path)
    gemini_web.add_argument("--phase", choices=("script", "proxy", "final"))
    gemini_web.add_argument("--account-hint")
    gemini_web.add_argument("--prompt-file", type=Path)
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


def _prepare(run_dir: Path) -> int:
    state, episode = _episode(run_dir)
    if state.stage is not Stage.CHUAN_BI:
        raise MvpError("prepare requires CHUAN_BI stage")
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
    job_path = build_operator_job(paths, source, transcript, shots)
    advance(run_dir, Stage.CHUAN_BI, Stage.QUAN_SAT)
    _write_next(
        run_dir,
        "QUAN_SAT theo Bo_nao_Antigravity/GEMINI.md; ghi su_that_tap_phim.json "
        "và scene_packets.json. "
        f"Job: {job_path}",
    )
    print(job_path)
    return 0


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
        _write_next(run_dir, "Kiểm tra scene_packets.json rồi chạy validate --artifact scene.")
    elif artifact == "scene":
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
        advance(run_dir, Stage.QUAN_SAT, Stage.LAP_STORYBOARD)
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


def _tts(run_dir: Path) -> int:
    started = time.perf_counter()
    state, episode = _episode(run_dir)
    if state.stage is not Stage.TAO_TTS:
        raise MvpError("tts requires TAO_TTS stage")
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
    expected_hash = job_payload["policy_sha256"]
    actual_hash = calculate_policy_sha256(episode.parents[3])
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


def _prompt(run_dir: Path) -> int:
    _, episode = _episode(run_dir)
    root = episode.parents[3]
    job_path = run_dir / "cong_viec_antigravity.json"
    if not job_path.is_file():
        raise MvpError("run has no cong_viec_antigravity.json; run prepare first")
    rendered = render_operator_prompt(
        run_dir,
        root / "Bo_nao_Antigravity" / "PROMPT_MOT_LAN_CHAY.md",
    )
    output = run_dir / "PROMPT_GUI_ANTIGRAVITY.txt"
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
        metadata = registry.load()
        if metadata is None:
            launch = launch_managed_chrome(root)
            metadata = GeminiSessionMetadata(
                run_id=run_dir.resolve().name,
                chrome_pid=launch.chrome_pid,
                debugger_address=launch.debugger_address,
                conversation_url=None,
                started_at=datetime.now(UTC).isoformat(),
                phase_turns={},
            )
            registry.save(metadata)
        else:
            metadata = registry.assert_attachable(run_dir.resolve().name)
            launch = connect_managed_chrome(metadata)
        try:
            turn_number = registry.increment_turn(
                run_dir.resolve().name,
                phase_upper,
                max_turns=policy.max_turns,
            )
            if prompt_override is None:
                prompt_path = Path(browser_packet.prompt_path)
                upload_paths = tuple(Path(path) for path in browser_packet.upload_paths)
            else:
                prompt_path = assert_inside_run(prompt_override, run_dir)
                upload_paths = ()
            prompt = prompt_path.read_text(encoding="utf-8")
            result = run_gemini_session(
                launch.page,
                policy=policy,
                account_hint=binding.account_hint,
                expected_account_sha256=binding.account_sha256,
                upload_paths=upload_paths,
                prompt=prompt,
                screenshot_path=(
                    run_dir
                    / "gemini_web"
                    / phase_upper.casefold()
                    / "screenshots"
                    / "session.png"
                ),
                chrome_pid=launch.chrome_pid,
                conversation_url=metadata.conversation_url,
            )
            registry.update_conversation(
                run_dir.resolve().name,
                result.observation.conversation_url,
            )
            dump_json(
                run_dir / "gemini_web" / "session.json",
                {
                    "run_id": run_dir.resolve().name,
                    "conversation_url": result.observation.conversation_url,
                    "phase": phase_upper,
                    "turn_number": turn_number,
                    "phase_turns": registry.load().phase_turns,
                },
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


def _gemini_web_run(run_dir: Path, phase: str) -> int:
    phase_upper = phase.upper()
    expected = {
        "SCRIPT": (Stage.VIET_LOI, Stage.CHO_GEMINI_SCRIPT),
        "PROXY": (Stage.PHAN_BIEN_VIDEO, Stage.CHO_GEMINI_PROXY),
        "FINAL": (Stage.CHO_GEMINI_FINAL, Stage.CHO_GEMINI_FINAL),
    }[phase_upper]
    state = read_state(run_dir)
    if state.stage is not expected[0]:
        raise MvpError(f"Gemini Web {phase.casefold()} run stage does not match")
    if expected[0] is not expected[1]:
        advance(run_dir, expected[0], expected[1])
    try:
        review = run_operator_phase(run_dir, phase_upper)
    except GeminiBrowserError as exc:
        code = _BROWSER_HUMAN_CODES.get(exc.code, "GEMINI_WEB_OPERATOR_THAT_BAI")
        mark_human_required(run_dir, code)
        _write_next(
            run_dir,
            f"Gemini Web dừng: {exc}. Xử lý trên cửa sổ Chrome rồi báo lại Codex.",
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
    return _accept_operator_review(run_dir, phase_upper, review)


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
        review = run_operator_phase(
            run_dir,
            phase_upper,
            prompt_override=prompt_path,
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
    if args.action == "continue":
        if args.phase is None or args.prompt_file is None:
            raise MvpError("gemini-web continue requires --phase and --prompt-file")
        return _gemini_web_continue(args.run, args.phase, args.prompt_file)
    if args.phase is None:
        raise MvpError("gemini-web run requires --phase")
    return _gemini_web_run(args.run, args.phase)


def _audit(run_dir: Path, phase: str, codex_review: Path | None) -> int:
    _, episode = _episode(run_dir)
    if phase == "script":
        return _audit_script(run_dir, episode)
    if phase == "engine":
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
            return _tts(args.run)
        if args.command == "render":
            return _render(args.run, args.quality)
        if args.command == "resume":
            return _resume(args.run, args.phase)
        if args.command == "audit":
            return _audit(args.run, args.phase, args.codex_review)
        if args.command == "gemini-web":
            return _gemini_web(args)
    except MvpError as exc:
        parser.error(str(exc))
    return 2
