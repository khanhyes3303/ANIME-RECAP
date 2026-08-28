from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from .errors import MvpError
from .workflow import Stage, advance, read_state
from .workspace import cleanup_run

_ARTIFACTS = {
    "su_that_tap_phim.json": Path("Su_that/su_that_tap_phim.json"),
    "scene_packets.json": Path("Su_that/scene_packets.json"),
    "kich_ban_review.json": Path("Kich_ban/kich_ban_review.json"),
    "tts_manifest.json": Path("TTS/tts_manifest.json"),
    "edl.json": Path("Ke_hoach_canh/edl.json"),
    "kiem_dinh.json": Path("Bao_cao/kiem_dinh.json"),
    "kiem_dinh_chat_luong.json": Path("Bao_cao/kiem_dinh_chat_luong.json"),
    "bao_cao_chat_luong.md": Path("Bao_cao/bao_cao_chat_luong.md"),
}


@dataclass(frozen=True, slots=True)
class FinalizationResult:
    status: str
    report_markdown: Path
    report_json: Path
    archive: Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _media_reference(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise MvpError(f"report media file does not exist: {path}")
    return {"path": str(path.resolve()), "sha256": _sha256(path)}


def _ffmpeg_version() -> str:
    result = subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return "unavailable"
    return result.stdout.splitlines()[0] if result.stdout else "unknown"


def build_report(run_dir: Path) -> tuple[Path, Path]:
    state = read_state(run_dir)
    if not state.episode_dir or not state.source_video:
        raise MvpError("run state lacks episode or source path")
    episode = Path(state.episode_dir)
    finals = sorted((episode / "Thanh_pham").glob("*.mp4"))
    if len(finals) > 1 or (state.stage is not Stage.CAN_CON_NGUOI_XU_LY and not finals):
        raise MvpError("report requires exactly one final MP4")
    status = "PASS" if state.stage in {Stage.DONG_GOI, Stage.HOAN_THANH} else state.stage.value
    final_reference = _media_reference(finals[0]) if finals else None
    report = {
        "status": status,
        "source": _media_reference(Path(state.source_video)),
        "final": final_reference,
        "tools": {"python": platform.python_version(), "ffmpeg": _ffmpeg_version()},
        "repair_history": [asdict(record) for record in state.repair_history],
    }
    report_dir = episode / "Bao_cao"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "bao_cao.json"
    markdown_path = report_dir / "bao_cao.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    final_lines = (
        f"- Thành phẩm: `{final_reference['path']}`\n"
        f"- SHA-256 thành phẩm: `{final_reference['sha256']}`\n"
        if final_reference
        else "- Thành phẩm: chưa tạo do cần con người xử lý\n"
    )
    markdown_path.write_text(
        "# Báo cáo tập anime\n\n"
        f"- Trạng thái: {status}\n"
        f"- Video nguồn: `{report['source']['path']}`\n"
        f"- SHA-256 nguồn: `{report['source']['sha256']}`\n"
        f"{final_lines}"
        f"- Số vòng sửa: {len(state.repair_history)}\n",
        encoding="utf-8",
    )
    return markdown_path, json_path


def create_handoff_zip(run_dir: Path, destination: Path) -> Path:
    state = read_state(run_dir)
    episode = Path(state.episode_dir)
    markdown_path, json_path = build_report(run_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    sources = {
        "bao_cao.md": markdown_path,
        "bao_cao.json": json_path,
        "run_state.json": run_dir / "run_state.json",
        **{name: episode / relative for name, relative in _ARTIFACTS.items()},
    }
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for archive_name, source in sources.items():
            if source.is_file():
                if source.suffix.lower() in {".mp4", ".mkv"}:
                    raise MvpError("video bytes are forbidden in the handoff ZIP")
                archive.write(source, archive_name)
    return destination.resolve()


def finalize_run(run_dir: Path, *, passed: bool) -> FinalizationResult:
    state = read_state(run_dir)
    if passed:
        if state.stage is not Stage.DONG_GOI:
            raise MvpError("only a DONG_GOI run can be finalized as PASS")
        state = advance(
            run_dir,
            Stage.DONG_GOI,
            Stage.HOAN_THANH,
            _package_completed=True,
        )
        status = "PASS"
    else:
        if state.stage is not Stage.CAN_CON_NGUOI_XU_LY:
            raise MvpError("failed finalization requires CAN_CON_NGUOI_XU_LY state")
        status = Stage.CAN_CON_NGUOI_XU_LY.value
    episode = Path(state.episode_dir)
    root = run_dir.resolve().parent.parent
    archive_name = "_".join(episode.parts[-3:]) + ".zip"
    destination = root / "Goi_gui_ChatGPT_Web" / archive_name
    archive = create_handoff_zip(run_dir, destination)
    markdown_path = episode / "Bao_cao" / "bao_cao.md"
    json_path = episode / "Bao_cao" / "bao_cao.json"
    cleanup_run(run_dir)
    return FinalizationResult(status, markdown_path, json_path, archive)
