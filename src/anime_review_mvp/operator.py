from __future__ import annotations

from dataclasses import dataclass

from .workflow import RunState, Stage


@dataclass(frozen=True, slots=True)
class OperatorDirective:
    """One deterministic instruction for the tagged Antigravity operator."""

    action: str
    situation_id: str = ""
    stop_code: str = ""


def plan_operator_step(
    state: RunState, *, editable_ids: tuple[str, ...]
) -> OperatorDirective:
    """Plan one safe step for the canonical whole-episode workflow.

    ``editable_ids`` remains in the signature for old callers and archived runs;
    canonical editorial routing deliberately does not iterate over it.
    """
    if state.stage is Stage.CHO_NGUOI_DUNG_DUYET_PROXY:
        return OperatorDirective("WAIT_FOR_USER_PROXY_APPROVAL")
    if state.stage is Stage.CAN_CON_NGUOI_XU_LY:
        return OperatorDirective("STOP", stop_code="HUMAN_REQUIRED")
    if state.stage is Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG:
        return OperatorDirective("PREPARE_STRUCTURE_JOB")
    if state.stage is Stage.CHO_ANTIGRAVITY_TINH_HUONG:
        return OperatorDirective("PREPARE_EPISODE_REVIEW_JOB", "__episode__")
    return OperatorDirective("RUN_ENGINE_STAGE")
