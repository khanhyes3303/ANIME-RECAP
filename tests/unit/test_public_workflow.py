from __future__ import annotations

import pytest

from anime_review_mvp.public_workflow import public_stage
from anime_review_mvp.workflow import Stage


@pytest.mark.parametrize(
    ("internal", "expected"),
    (
        (Stage.TRICH_XUAT_BANG_CHUNG, "PHAN_TICH"),
        (Stage.CHO_ANTIGRAVITY_TINH_HUONG, "VIET_REVIEW"),
        (Stage.TAO_TTS_TINH_HUONG, "TAO_VOICE_VA_KHOP_CANH"),
        (Stage.DUNG_PROXY, "DUNG_VIDEO"),
        (Stage.KIEM_DINH_PROXY, "KIEM_TRA"),
        (Stage.CHO_NGUOI_DUNG_DUYET_PROXY, "CHO_NGUOI_DUNG_DUYET_PROXY"),
    ),
)
def test_public_stage_projection(internal: Stage, expected: str) -> None:
    assert public_stage(internal).value == expected


def test_every_internal_stage_has_a_public_projection() -> None:
    assert {public_stage(stage).value for stage in Stage} <= {
        "PHAN_TICH",
        "VIET_REVIEW",
        "TAO_VOICE_VA_KHOP_CANH",
        "DUNG_VIDEO",
        "KIEM_TRA",
        "CHO_NGUOI_DUNG_DUYET_PROXY",
    }
