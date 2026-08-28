from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.workflow import (
    Stage,
    advance,
    new_state,
    read_state,
    record_repair,
)


def test_state_machine_is_linear_and_fail_closed(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run")

    with pytest.raises(MvpError, match="transition"):
        advance(state.run_dir, Stage.CHUAN_BI, Stage.TAO_TTS)


def test_state_advances_only_from_persisted_expected_stage(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run")
    advanced = advance(state.run_dir, Stage.CHUAN_BI, Stage.QUAN_SAT)

    assert advanced.stage is Stage.QUAN_SAT
    with pytest.raises(MvpError, match="expected"):
        advance(state.run_dir, Stage.CHUAN_BI, Stage.QUAN_SAT)


def test_third_failed_repair_becomes_human_required(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run")
    for _ in range(3):
        state = record_repair(
            state.run_dir, "SUA_NOI_DUNG", ("UNSUPPORTED_CLAIM",)
        )

    assert state.stage is Stage.CAN_CON_NGUOI_XU_LY
    assert len(read_state(state.run_dir).repair_history) == 3
    with pytest.raises(MvpError, match="human"):
        record_repair(
            state.run_dir, "SUA_NOI_DUNG", ("UNSUPPORTED_CLAIM",)
        )


def test_only_engine_audit_can_mark_run_complete(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run", stage=Stage.KIEM_DINH_VIDEO)
    with pytest.raises(MvpError, match="engine audit"):
        advance(state.run_dir, Stage.KIEM_DINH_VIDEO, Stage.HOAN_THANH)

    completed = advance(
        state.run_dir,
        Stage.KIEM_DINH_VIDEO,
        Stage.HOAN_THANH,
        _engine_audit_passed=True,
    )
    assert completed.stage is Stage.HOAN_THANH


def test_content_repair_returns_to_codex_editor(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run", stage=Stage.KIEM_DINH_VIDEO)

    repaired = record_repair(state.run_dir, "SUA_NOI_DUNG", ("SCENE_MISMATCH",))

    assert repaired.stage is Stage.CODEX_BIEN_TAP
