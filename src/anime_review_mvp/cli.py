from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .antigravity import (
    build_operator_job,
    load_audit,
    load_scene_packets,
    load_script,
    load_truth,
)
from .errors import MvpError
from .jsonio import dump_json, load_json
from .media import (
    detect_shots,
    extract_inspection_assets,
    probe_source,
    transcribe_english,
)
from .models import EdlDocument, ShotDocument, SourceRef, TtsManifest
from .package import finalize_run
from .render import render_review
from .tts import synthesize_script
from .validation import (
    build_edl_from_scene_packets,
    coverage_ratio,
    validate_audit,
    validate_edl,
    validate_scene_packets,
    validate_script,
    validate_truth,
    validate_voice_lock,
)
from .workflow import Stage, advance, new_state, read_state, record_repair
from .workspace import create_job


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
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--run", required=True, type=Path)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--run", required=True, type=Path)
    validate.add_argument(
        "--artifact", required=True, choices=("truth", "scene", "script", "edl")
    )
    tts = subparsers.add_parser("tts")
    tts.add_argument("--run", required=True, type=Path)
    render = subparsers.add_parser("render")
    render.add_argument("--run", required=True, type=Path)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--run", required=True, type=Path)
    audit.add_argument("--phase", required=True, choices=("script", "video"))
    package = subparsers.add_parser("package")
    package.add_argument("--run", required=True, type=Path)
    return parser


def _start(args: argparse.Namespace) -> int:
    root = Path.cwd()
    paths = create_job(root, args.anime, args.season, args.episode, args.video)
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


def _write_next(run_dir: Path, instruction: str) -> None:
    state = read_state(run_dir)
    payload = {
        "stage": state.stage.value,
        "instruction": instruction,
        "run_dir": str(state.run_dir),
    }
    (run_dir / "next_action.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _prepare(run_dir: Path) -> int:
    state, episode = _episode(run_dir)
    if state.stage is not Stage.CHUAN_BI:
        raise MvpError("prepare requires CHUAN_BI stage")
    source = probe_source(Path(state.source_video))
    dump_json(episode / "Dau_vao" / "source_ref.json", source)
    transcript = transcribe_english(
        Path(state.source_video), run_dir / "transcript_english.json"
    )
    shots = detect_shots(Path(state.source_video), source.duration_ms)
    dump_json(run_dir / "shots.json", ShotDocument(shots))
    extract_inspection_assets(
        Path(state.source_video), shots, run_dir / "inspection_frames"
    )
    paths = _job_paths_from_state(state, episode)
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
        advance(run_dir, Stage.QUAN_SAT, Stage.VIET_KICH_BAN)
        _write_next(run_dir, "VIET_KICH_BAN và ghi kich_ban_review.json.")
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
        truth = load_truth(
            episode / "Su_that" / "su_that_tap_phim.json",
            source_duration_ms=source.duration_ms,
        )
        tts = load_json(episode / "TTS" / "tts_manifest.json", TtsManifest)
        edl = load_json(episode / "Ke_hoach_canh" / "edl.json", EdlDocument)
        script = load_script(episode / "Kich_ban" / "kich_ban_review.json")
        validate_edl(edl, source.duration_ms, tts, truth)
        packets = load_scene_packets(episode / "Su_that" / "scene_packets.json")
        validate_voice_lock(packets.packets, script, tts, edl)
        advance(run_dir, Stage.LAP_EDL, Stage.DUNG_VIDEO)
        _write_next(run_dir, "Chạy render để dựng video TTS-only.")
    return 0


def _tts(run_dir: Path) -> int:
    _, episode = _episode(run_dir)
    if read_state(run_dir).stage is not Stage.TAO_TTS:
        raise MvpError("tts requires TAO_TTS stage")
    script = load_script(episode / "Kich_ban" / "kich_ban_review.json")
    tts = synthesize_script(script, episode / "TTS")
    packets = load_scene_packets(episode / "Su_that" / "scene_packets.json")
    edl = build_edl_from_scene_packets(packets.packets, script, tts)
    dump_json(episode / "Ke_hoach_canh" / "edl.json", edl)
    advance(run_dir, Stage.TAO_TTS, Stage.LAP_EDL)
    _write_next(
        run_dir,
        "EDL đã tạo từ scene packet và duration TTS thật; chạy validate --artifact edl.",
    )
    return 0


def _render(run_dir: Path) -> int:
    state, episode = _episode(run_dir)
    if state.stage is not Stage.DUNG_VIDEO:
        raise MvpError("render requires DUNG_VIDEO stage")
    edl = load_json(episode / "Ke_hoach_canh" / "edl.json", EdlDocument)
    tts = load_json(episode / "TTS" / "tts_manifest.json", TtsManifest)
    output = episode / "Thanh_pham" / "review_anime.mp4"
    render_review(Path(state.source_video), Path(tts.narration_wav_path), edl, output)
    advance(run_dir, Stage.DUNG_VIDEO, Stage.KIEM_DINH_VIDEO)
    _write_next(run_dir, "Xem MP4 cuối, cập nhật kiem_dinh.json rồi chạy audit --phase video.")
    print(output)
    return 0


def _audit(run_dir: Path, phase: str) -> int:
    _, episode = _episode(run_dir)
    audit = load_audit(episode / "Bao_cao" / "kiem_dinh.json")
    blocking_codes = tuple(
        finding.code for finding in audit.findings if finding.severity == "ERROR"
    )
    if not audit.passed or blocking_codes:
        codes = blocking_codes or ("AUDIT_NOT_PASSED",)
        scene_markers = ("SCENE", "EDL", "FOOTAGE", "SYNC")
        owner = (
            "SUA_EDL"
            if any(marker in code for code in codes for marker in scene_markers)
            else "SUA_NOI_DUNG"
        )
        state = record_repair(run_dir, owner, codes)
        repair_count = len(state.repair_history)
        _write_next(
            run_dir, f"{owner}: sửa lỗi {', '.join(codes)}; vòng {repair_count}/3."
        )
        return 1
    if phase == "script":
        advance(run_dir, Stage.KIEM_DINH_KICH_BAN, Stage.TAO_TTS)
        _write_next(run_dir, "Chạy TTS giọng BV074_streaming.")
    else:
        script = load_script(episode / "Kich_ban" / "kich_ban_review.json")
        tts = load_json(episode / "TTS" / "tts_manifest.json", TtsManifest)
        edl = load_json(episode / "Ke_hoach_canh" / "edl.json", EdlDocument)
        packets = load_scene_packets(episode / "Su_that" / "scene_packets.json")
        validate_voice_lock(packets.packets, script, tts, edl)
        measured = coverage_ratio(script, tts)
        validate_audit(audit, measured)
        advance(run_dir, Stage.KIEM_DINH_VIDEO, Stage.DONG_GOI)
        _write_next(run_dir, "Kiểm định đạt; chạy package.")
    return 0


def _package(run_dir: Path) -> int:
    result = finalize_run(run_dir, passed=True)
    print(result.archive)
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
        if args.command == "validate":
            return _validate(args.run, args.artifact)
        if args.command == "tts":
            return _tts(args.run)
        if args.command == "render":
            return _render(args.run)
        if args.command == "audit":
            return _audit(args.run, args.phase)
        if args.command == "package":
            return _package(args.run)
    except MvpError as exc:
        parser.error(str(exc))
    return 2
