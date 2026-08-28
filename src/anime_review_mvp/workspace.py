from __future__ import annotations

import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from .errors import MvpError

_INVALID_WINDOWS_NAME = re.compile(r'[<>:"/\\|?*]')


@dataclass(frozen=True, slots=True)
class JobKey:
    anime: str
    season: int
    episode: int


@dataclass(frozen=True, slots=True)
class JobPaths:
    root: Path
    key: JobKey
    source_video: Path
    episode_dir: Path
    input_dir: Path
    truth_dir: Path
    script_dir: Path
    tts_dir: Path
    edl_dir: Path
    final_dir: Path
    report_dir: Path
    temp_dir: Path

    @property
    def episode_artifact_dirs(self) -> tuple[Path, ...]:
        return (
            self.input_dir,
            self.truth_dir,
            self.script_dir,
            self.tts_dir,
            self.edl_dir,
            self.final_dir,
            self.report_dir,
        )


@dataclass(frozen=True, slots=True)
class PublishResult:
    final_path: str
    backup_path: str | None


def create_job(
    root: Path,
    anime: str,
    season: int,
    episode: int,
    video: Path,
    *,
    revision: bool = False,
) -> JobPaths:
    if season < 1 or episode < 1:
        raise MvpError("season and episode must be positive")
    source = video.resolve(strict=True)
    if not source.is_file():
        raise MvpError("source video must be a file")
    anime_dir_name = _safe_anime_name(anime)
    project_root = root.resolve()
    episode_dir = (
        project_root
        / "Kho_Anime"
        / anime_dir_name
        / f"Mua_{season:02d}"
        / f"Tap_{episode:03d}"
    )
    final_dir = episode_dir / "Thanh_pham"
    if not revision and final_dir.is_dir() and any(
        item.is_file() and item.suffix.lower() == ".mp4" for item in final_dir.iterdir()
    ):
        raise MvpError("MVP refuses to overwrite an existing final MP4")
    paths = JobPaths(
        root=project_root,
        key=JobKey(anime.strip(), season, episode),
        source_video=source,
        episode_dir=episode_dir,
        input_dir=episode_dir / "Dau_vao",
        truth_dir=episode_dir / "Su_that",
        script_dir=episode_dir / "Kich_ban",
        tts_dir=episode_dir / "TTS",
        edl_dir=episode_dir / "Ke_hoach_canh",
        final_dir=final_dir,
        report_dir=episode_dir / "Bao_cao",
        temp_dir=project_root / "Tam_dang_xu_ly" / uuid.uuid4().hex,
    )
    for directory in (*paths.episode_artifact_dirs, paths.temp_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def publish_candidate(
    candidate: Path,
    final: Path,
    backup_dir: Path,
) -> PublishResult:
    candidate_path = candidate.resolve(strict=True)
    if not candidate_path.is_file() or candidate_path.suffix.lower() != ".mp4":
        raise MvpError("review candidate must be an MP4 file")
    final_path = final.resolve(strict=False)
    if final_path.suffix.lower() != ".mp4":
        raise MvpError("final review path must be an MP4 file")
    final_path.parent.mkdir(parents=True, exist_ok=True)

    backup_path: Path | None = None
    if final_path.is_file():
        backup_root = backup_dir.resolve(strict=False)
        backup_root.mkdir(parents=True, exist_ok=True)
        backup_path = backup_root / "review_anime_previous.mp4"
        if backup_path.exists():
            backup_path = backup_root / f"review_anime_previous_{uuid.uuid4().hex}.mp4"
        shutil.copy2(final_path, backup_path)
    os.replace(candidate_path, final_path)
    return PublishResult(
        str(final_path),
        str(backup_path) if backup_path is not None else None,
    )


def assert_inside_run(path: Path, run_root: Path) -> Path:
    root = run_root.resolve(strict=True)
    resolved = path.resolve(strict=False)
    if resolved == root or root not in resolved.parents:
        raise MvpError("cleanup target is outside the exact run directory")
    return resolved


def cleanup_run(run_root: Path) -> None:
    root = run_root.resolve(strict=True)
    if root.parent.name != "Tam_dang_xu_ly":
        raise MvpError("run directory is not directly under Tam_dang_xu_ly")
    for child in root.iterdir():
        assert_inside_run(child, root)
    shutil.rmtree(root)


def _safe_anime_name(name: str) -> str:
    cleaned = _INVALID_WINDOWS_NAME.sub("_", name.strip()).rstrip(". ")
    if not cleaned or cleaned in {".", ".."}:
        raise MvpError("anime name is invalid")
    return cleaned
