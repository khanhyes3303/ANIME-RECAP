from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .errors import MvpError
from .gemini_web import sha256_file
from .jsonio import load_json
from .models import AtomicStoryboard, TruthDocument
from .workflow import read_state

Runner = Callable[..., Any]
_PHASES = {"SCRIPT", "PROXY", "FINAL"}


@dataclass(frozen=True, slots=True)
class GeminiBrowserPacket:
    phase: str
    media_path: str
    manifest_path: str
    prompt_path: str
    upload_paths: tuple[str, ...]
    packet_sha256: str
    beat_ids: tuple[str, ...]


def _inside_run(path: Path, run_dir: Path, label: str) -> Path:
    if path.is_symlink():
        raise MvpError(f"Gemini packet {label} may not be a symlink")
    root = run_dir.resolve(strict=True)
    resolved = path.resolve(strict=False)
    if resolved == root or root not in resolved.parents:
        raise MvpError(f"Gemini packet {label} is outside run")
    return resolved


def _reset_packet_dir(run_dir: Path, phase: str) -> Path:
    packet_dir = run_dir / "gemini_web" / phase.casefold() / "operator_packet"
    if packet_dir.exists():
        safe = _inside_run(packet_dir, run_dir, "directory")
        if safe.is_dir():
            shutil.rmtree(safe)
        else:
            safe.unlink()
    packet_dir.mkdir(parents=True)
    return packet_dir


def _overlaps(start_ms: int, end_ms: int, excluded_start: int, excluded_end: int) -> bool:
    return start_ms < excluded_end and end_ms > excluded_start


def _selected_beats(
    storyboard: AtomicStoryboard,
    beat_ids: tuple[str, ...] | None,
) -> tuple[object, ...]:
    available = {beat.beat_id: beat for beat in storyboard.beats}
    selected_ids = beat_ids or tuple(available)
    if not selected_ids or len(selected_ids) != len(set(selected_ids)):
        raise MvpError("Gemini packet beat selection is invalid")
    unknown = tuple(beat_id for beat_id in selected_ids if beat_id not in available)
    if unknown:
        raise MvpError(f"Gemini packet references unknown beat IDs: {unknown}")
    return tuple(available[beat_id] for beat_id in selected_ids)


def _timestamp(milliseconds: int) -> str:
    seconds, millis = divmod(milliseconds, 1_000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def _drawtext_label(beat_id: str, start_ms: int) -> str:
    timestamp = _timestamp(start_ms).replace(":", r"\:")
    return (
        "drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':"
        f"text='{beat_id} | {timestamp}':x=24:y=24:fontsize=28:"
        "fontcolor=white:box=1:boxcolor=black@0.75"
    )


def build_script_evidence_media(
    source: Path,
    beats: tuple[object, ...],
    output: Path,
    runner: Runner = subprocess.run,
) -> None:
    filters: list[str] = []
    labels: list[str] = []
    index = 0
    for beat in beats:
        for source_range in beat.source_ranges:
            start = source_range.source_start_ms / 1_000
            end = source_range.source_end_ms / 1_000
            label = f"clip{index}"
            filters.append(
                f"[0:v:0]trim=start={start:.3f}:end={end:.3f},"
                "setpts=PTS-STARTPTS,scale=-2:720,"
                f"{_drawtext_label(beat.beat_id, source_range.source_start_ms)}[{label}]"
            )
            labels.append(f"[{label}]")
            index += 1
    if not labels:
        raise MvpError("Gemini SCRIPT packet has no source ranges")
    filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[video]")
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(source),
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[video]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "28",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    result = runner(command, capture_output=True, text=True, check=False)
    if result.returncode != 0 or not output.is_file():
        raise MvpError(f"Gemini SCRIPT packet render failed: {result.stderr.strip()}")


def _prompt(
    phase: str,
    beat_ids: tuple[str, ...],
    *,
    candidate_name: str | None = None,
) -> str:
    verdicts = (
        "NOT_APPLICABLE"
        if phase == "SCRIPT"
        else "MATCH, VOICE_AHEAD, VOICE_BEHIND, SCENE_MISMATCH, ACTION_MISMATCH"
    )
    example_verdict = "NOT_APPLICABLE" if phase == "SCRIPT" else "MATCH"
    phase_label = "SCRIPT" if phase == "SCRIPT" else "VIDEO"
    media_instructions = (
        "script_evidence.mp4 là trích đoạn nguồn dùng để kiểm nội dung lời kể; "
        "anchors.json chứa các mốc SOURCE hợp lệ. "
        if phase == "SCRIPT"
        else (
            "source_episode.mp4 là video tập gốc đầy đủ; "
            f"{candidate_name} là video cần kiểm định; mapping.json ánh xạ SOURCE sang "
            "PROGRAM; source_anchors.json và program_anchors.json chứa các anchor_id "
            "hợp lệ của hai timeline. Phải xem và đối chiếu cả hai video. "
        )
    )
    evidence_requirement = (
        "evidence_refs phải chứa TOÀN BỘ anchor_id START/MIDDLE/END của SOURCE cho "
        "mọi range thuộc beat. "
        if phase == "SCRIPT"
        else "evidence_refs phải chứa TOÀN BỘ anchor_id START/MIDDLE/END của cả SOURCE "
        "và PROGRAM cho mọi range thuộc beat. "
    )
    return (
        f"Kiểm định phase {phase} cho đúng các beat: {', '.join(beat_ids)}. "
        + media_instructions
        + "Đọc video và manifest đã tải lên theo thứ tự thời gian. Loại intro, opening, "
        "ending, credits và title card không phục vụ cốt truyện. So sánh hình, hành động "
        "và lời review Việt; không đoán khi thiếu bằng chứng. Trả đúng một JSON object, "
        "không markdown và không thêm trường ngoài schema sau: "
        f'{{"phase":"{phase_label}","producer_context_id":"chuỗi không rỗng",'
        '"critic_context_id":"chuỗi không rỗng","beat_reviews":['
        '{"beat_id":"beat-...","finding_codes":[],"evidence_refs":'
        '["anchor_id từ anchors.json"],"observed_visual":"mô tả hình thấy thật",'
        '"narration_summary":"tóm tắt lời review",'
        f'"sync_verdict":"{example_verdict}","note":"nhận xét"}}]}}. '
        "Phải đủ đúng một beat_reviews cho mỗi beat. "
        + evidence_requirement
        + "Mọi anchor_id phải có thật trong file anchors tương ứng. Không dùng các "
        "trường document_type, "
        "policy_version, overall_verdict hoặc notes. "
        f"sync_verdict chỉ dùng: {verdicts}. Mọi verdict khác MATCH phải có cùng code "
        "trong finding_codes và evidence_refs phải trỏ đúng beat/timestamp burn-in."
    )


def _write_manifest(
    path: Path,
    *,
    phase: str,
    beat_ids: tuple[str, ...],
    files: tuple[Path, ...],
    excluded_regions: tuple[object, ...],
) -> None:
    payload = {
        "phase": phase,
        "beat_ids": list(beat_ids),
        "files": [
            {"path": str(file.resolve()), "sha256": sha256_file(file)} for file in files
        ],
        "excluded_regions": [asdict(region) for region in excluded_regions],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def build_browser_packet(
    run_dir: Path,
    phase: str,
    *,
    beat_ids: tuple[str, ...] | None = None,
    runner: Runner = subprocess.run,
) -> GeminiBrowserPacket:
    phase_upper = phase.upper()
    if phase_upper not in _PHASES:
        raise MvpError("Gemini packet phase is invalid")
    state = read_state(run_dir)
    episode = Path(state.episode_dir)
    source = Path(state.source_video)
    if not source.is_file() or source.is_symlink():
        raise MvpError("Gemini packet source video is invalid")
    storyboard_path = episode / "Kich_ban" / "atomic_storyboard.json"
    truth_path = episode / "Su_that" / "su_that_tap_phim.json"
    storyboard = load_json(storyboard_path, AtomicStoryboard)
    truth = load_json(truth_path, TruthDocument)
    beats = _selected_beats(storyboard, beat_ids)
    selected_ids = tuple(beat.beat_id for beat in beats)
    excluded = tuple(region for region in truth.source_regions if region.decision == "EXCLUDE")
    for beat in beats:
        for source_range in beat.source_ranges:
            if any(
                _overlaps(
                    source_range.source_start_ms,
                    source_range.source_end_ms,
                    region.start_ms,
                    region.end_ms,
                )
                for region in excluded
            ):
                raise MvpError(
                    f"beat {beat.beat_id} overlaps an excluded source region"
                )

    packet_dir = _reset_packet_dir(run_dir, phase_upper)
    prompt_path = packet_dir / "prompt.txt"
    evidence_files: tuple[Path, ...] = ()
    if phase_upper == "SCRIPT":
        media = packet_dir / "script_evidence.mp4"
        supplemental = packet_dir / "storyboard.json"
        source_anchors = run_dir / "atomic_evidence" / "source" / "anchors.json"
        if not source_anchors.is_file() or source_anchors.is_symlink():
            raise MvpError("Gemini SCRIPT packet source anchors are missing")
        anchors = packet_dir / "anchors.json"
        build_script_evidence_media(source, beats, media, runner)
        shutil.copy2(storyboard_path, supplemental)
        shutil.copy2(source_anchors, anchors)
        evidence_files = (anchors,)
        prompt_path.write_text(_prompt(phase_upper, selected_ids), encoding="utf-8")
    else:
        candidate = (
            run_dir / "proxy" / "review_proxy.mp4"
            if phase_upper == "PROXY"
            else run_dir / "final_candidate.mp4"
        )
        if not candidate.is_file() or candidate.is_symlink():
            raise MvpError(f"Gemini {phase_upper} packet candidate is missing")
        media_name = "proxy_review.mp4" if phase_upper == "PROXY" else "final_candidate.mp4"
        media = packet_dir / media_name
        supplemental = packet_dir / "mapping.json"
        shutil.copy2(candidate, media)
        mapping = episode / "Ke_hoach_canh" / "atomic_edl.json"
        if not mapping.is_file() or mapping.is_symlink():
            raise MvpError(f"Gemini {phase_upper} packet mapping is missing")
        shutil.copy2(mapping, supplemental)
        source_anchors = run_dir / "atomic_evidence" / "source" / "anchors.json"
        if not source_anchors.is_file() or source_anchors.is_symlink():
            raise MvpError(f"Gemini {phase_upper} packet source anchors are missing")
        program_anchors = run_dir / "atomic_evidence" / "program" / "anchors.json"
        if not program_anchors.is_file() or program_anchors.is_symlink():
            raise MvpError(f"Gemini {phase_upper} packet program anchors are missing")
        source_media = packet_dir / "source_episode.mp4"
        source_anchor_copy = packet_dir / "source_anchors.json"
        program_anchor_copy = packet_dir / "program_anchors.json"
        shutil.copy2(source, source_media)
        shutil.copy2(source_anchors, source_anchor_copy)
        shutil.copy2(program_anchors, program_anchor_copy)
        evidence_files = (source_media, source_anchor_copy, program_anchor_copy)
        prompt_path.write_text(
            _prompt(phase_upper, selected_ids, candidate_name=media_name),
            encoding="utf-8",
        )
    manifest = packet_dir / "manifest.json"
    content_files = (media, supplemental, *evidence_files, prompt_path)
    _write_manifest(
        manifest,
        phase=phase_upper,
        beat_ids=selected_ids,
        files=content_files,
        excluded_regions=excluded,
    )
    packet = GeminiBrowserPacket(
        phase_upper,
        str(media.resolve()),
        str(manifest.resolve()),
        str(prompt_path.resolve()),
        tuple(
            str(path.resolve())
            for path in (media, supplemental, *evidence_files, manifest)
        ),
        sha256_file(manifest),
        selected_ids,
    )
    verify_packet(packet, run_dir)
    return packet


def sha256_packet(packet: GeminiBrowserPacket) -> str:
    return sha256_file(Path(packet.manifest_path))


def verify_packet(packet: GeminiBrowserPacket, run_dir: Path) -> GeminiBrowserPacket:
    if packet.phase not in _PHASES:
        raise MvpError("Gemini packet phase is invalid")
    manifest_path = _inside_run(Path(packet.manifest_path), run_dir, "manifest")
    if not manifest_path.is_file() or sha256_file(manifest_path) != packet.packet_sha256:
        raise MvpError("Gemini packet manifest hash does not match")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["phase"] != packet.phase or tuple(manifest["beat_ids"]) != packet.beat_ids:
            raise MvpError("Gemini packet manifest identity does not match")
        for item in manifest["files"]:
            path = _inside_run(Path(item["path"]), run_dir, "file")
            if not path.is_file() or sha256_file(path) != item["sha256"]:
                raise MvpError("Gemini packet file hash does not match")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MvpError("Gemini packet manifest is invalid") from exc
    prompt_path = str(_inside_run(Path(packet.prompt_path), run_dir, "prompt"))
    expected_uploads = {
        str(_inside_run(Path(item["path"]), run_dir, "manifest file"))
        for item in manifest["files"]
        if str(Path(item["path"]).resolve()) != prompt_path
    }
    expected_uploads.add(str(manifest_path))
    actual_uploads = {
        str(_inside_run(Path(path), run_dir, "upload")) for path in packet.upload_paths
    }
    if not expected_uploads.issubset(actual_uploads):
        raise MvpError("Gemini packet upload set is incomplete")
    return packet
