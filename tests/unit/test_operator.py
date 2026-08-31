from __future__ import annotations

from pathlib import Path

from anime_review_mvp.operator import plan_operator_step
from anime_review_mvp.workflow import RunState, Stage


def _state(
    *,
    stage: Stage,
    locked: tuple[str, ...] = (),
    current_situation_id: str = "",
) -> RunState:
    return RunState(
        run_dir=Path("run"),
        stage=stage,
        locked_situation_ids=locked,
        current_situation_id=current_situation_id,
    )


def test_operator_requests_structure_job_at_structure_wait_stage() -> None:
    directive = plan_operator_step(
        _state(stage=Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG),
        editable_ids=(),
    )

    assert directive.action == "PREPARE_STRUCTURE_JOB"


def test_operator_requests_next_unlocked_situation_without_a_fixed_count() -> None:
    directive = plan_operator_step(
        _state(stage=Stage.CHO_ANTIGRAVITY_TINH_HUONG, locked=("situation-001",)),
        editable_ids=("situation-001", "situation-002", "situation-003"),
    )

    assert directive.action == "PREPARE_SITUATION_JOB"
    assert directive.situation_id == "situation-002"


def test_operator_runs_engine_stage_when_every_editable_situation_is_locked() -> None:
    directive = plan_operator_step(
        _state(
            stage=Stage.CHO_ANTIGRAVITY_TINH_HUONG,
            locked=("situation-001", "situation-002"),
        ),
        editable_ids=("situation-001", "situation-002"),
    )

    assert directive.action == "RUN_ENGINE_STAGE"


def test_operator_stops_only_at_user_proxy_gate() -> None:
    directive = plan_operator_step(
        _state(stage=Stage.CHO_NGUOI_DUNG_DUYET_PROXY),
        editable_ids=(),
    )

    assert directive.action == "WAIT_FOR_USER_PROXY_APPROVAL"


def test_operator_stops_for_human_required_runs() -> None:
    directive = plan_operator_step(
        _state(stage=Stage.CAN_CON_NGUOI_XU_LY),
        editable_ids=(),
    )

    assert directive.action == "STOP"
    assert directive.stop_code == "HUMAN_REQUIRED"
