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
def test_tagged_operator_creates_one_job_for_every_episode_size(count: int) -> None:
    editable = tuple(f"situation-{index:03d}" for index in range(1, count + 1))
    directive = plan_operator_step(
        _state(Stage.CHO_ANTIGRAVITY_TINH_HUONG), editable_ids=editable
    )

    assert directive.action == "PREPARE_EPISODE_REVIEW_JOB"
    assert directive.situation_id == "__episode__"


def test_operator_ignores_legacy_locked_prefix() -> None:
    editable = tuple(f"situation-{index:03d}" for index in range(1, 5))
    directive = plan_operator_step(
        _state(
            Stage.CHO_ANTIGRAVITY_TINH_HUONG,
            ("situation-001", "situation-002"),
        ),
        editable_ids=editable,
    )
    assert directive.situation_id == "__episode__"
    assert directive.action == "PREPARE_EPISODE_REVIEW_JOB"


def test_operator_only_waits_for_user_at_proxy_gate() -> None:
    directive = plan_operator_step(
        _state(Stage.CHO_NGUOI_DUNG_DUYET_PROXY), editable_ids=()
    )
    assert directive.action == "WAIT_FOR_USER_PROXY_APPROVAL"
