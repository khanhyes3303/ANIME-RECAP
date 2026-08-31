from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.reference_profile import load_reference_profile


def test_reference_profile_requires_real_video_with_matching_hash(tmp_path: Path) -> None:
    video = tmp_path / "reference.mp4"
    video.write_bytes(b"reference-video")
    config = tmp_path / "reference_review.json"
    config.write_text(
        json.dumps(
            {
                "video_path": str(video),
                "sha256": "0" * 64,
                "normal_pause_min_ms": 350,
                "normal_pause_max_ms": 900,
                "hard_pause_max_ms": 1200,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(MvpError, match="REFERENCE_VIDEO_HASH_MISMATCH"):
        load_reference_profile(config)

    payload = json.loads(config.read_text(encoding="utf-8"))
    payload["sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
    config.write_text(json.dumps(payload), encoding="utf-8")

    profile = load_reference_profile(config)
    assert profile.video_path == str(video.resolve())
    assert profile.hard_pause_max_ms == 1_200
