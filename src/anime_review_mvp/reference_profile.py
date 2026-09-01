from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .errors import MvpError


@dataclass(frozen=True, slots=True)
class ReferenceStyleProfile:
    video_path: str
    sha256: str
    normal_pause_min_ms: int
    normal_pause_max_ms: int
    hard_pause_max_ms: int


def load_reference_profile(config_path: Path) -> ReferenceStyleProfile:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        video = Path(payload["video_path"]).resolve(strict=True)
        expected_hash = str(payload["sha256"])
        normal_min = int(payload["normal_pause_min_ms"])
        normal_max = int(payload["normal_pause_max_ms"])
        hard_max = int(payload["hard_pause_max_ms"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MvpError("REFERENCE_VIDEO_CONFIG_INVALID") from exc
    if not video.is_file() or video.suffix.casefold() not in {".mp4", ".mkv", ".mov"}:
        raise MvpError("REFERENCE_VIDEO_MISSING")
    actual_hash = hashlib.sha256(video.read_bytes()).hexdigest()
    if actual_hash != expected_hash:
        raise MvpError("REFERENCE_VIDEO_HASH_MISMATCH")
    if not 0 <= normal_min <= normal_max <= hard_max <= 600:
        raise MvpError("REFERENCE_PAUSE_PROFILE_INVALID")
    return ReferenceStyleProfile(str(video), expected_hash, normal_min, normal_max, hard_max)
