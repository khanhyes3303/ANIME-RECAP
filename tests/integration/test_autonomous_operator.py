"""Contract-level checks for the tagged operator handoff.

The integration boundary intentionally stops at the Antigravity handoff: the
local operator prepares one deterministic job, and the tagged parent completes
it before invoking ``operator`` again.  No episode-specific content is baked
into these tests.
"""

from pathlib import Path

import pytest

from anime_review_mvp.operator import plan_operator_step
from anime_review_mvp.workflow import RunState, Stage


def _state(stage: Stage, locked: tuple[str, ...] = ()) -> RunState:
    return RunState(run_dir=Path("run"), stage=stage, locked_situation_ids=locked)


@pytest.mark.parametrize("count", (1, 3, 47))
def test_tagged_operator_selects_every_dynamic_situation_without_relay(count: int) -> None:
    editable = tuple(f"situation-{index:03d}" for index in range(1, count + 1))
    locked: tuple[str, ...] = ()
    selected: list[str] = []

    while len(selected) < count:
        directive = plan_operator_step(
            _state(Stage.CHO_ANTIGRAVITY_TINH_HUONG, locked),
            editable_ids=editable,
        )
        assert directive.action == "PREPARE_SITUATION_JOB"
        assert directive.situation_id not in selected
        selected.append(directive.situation_id)
        locked = (*locked, directive.situation_id)

    assert tuple(selected) == editable
    assert plan_operator_step(
        _state(Stage.CHO_ANTIGRAVITY_TINH_HUONG, locked), editable_ids=editable
    ).action == "RUN_ENGINE_STAGE"


def test_operator_is_resumable_from_locked_prefix() -> None:
    editable = tuple(f"situation-{index:03d}" for index in range(1, 5))
    directive = plan_operator_step(
        _state(
            Stage.CHO_ANTIGRAVITY_TINH_HUONG,
            ("situation-001", "situation-002"),
        ),
        editable_ids=editable,
    )
    assert directive.situation_id == "situation-003"
    assert directive.action == "PREPARE_SITUATION_JOB"


def test_operator_only_waits_for_user_at_proxy_gate() -> None:
    directive = plan_operator_step(
        _state(Stage.CHO_NGUOI_DUNG_DUYET_PROXY), editable_ids=()
    )
    assert directive.action == "WAIT_FOR_USER_PROXY_APPROVAL"
