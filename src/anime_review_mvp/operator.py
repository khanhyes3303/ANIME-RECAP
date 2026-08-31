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
    """Plan one safe step without assuming a fixed number of situations."""
    if state.stage is Stage.CHO_NGUOI_DUNG_DUYET_PROXY:
        return OperatorDirective("WAIT_FOR_USER_PROXY_APPROVAL")
    if state.stage is Stage.CAN_CON_NGUOI_XU_LY:
        return OperatorDirective("STOP", stop_code="HUMAN_REQUIRED")
    if state.stage is Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG:
        return OperatorDirective("PREPARE_STRUCTURE_JOB")
    if state.stage is Stage.CHO_ANTIGRAVITY_TINH_HUONG:
        next_id = next(
            (item for item in editable_ids if item not in state.locked_situation_ids),
            "",
        )
        if next_id:
            return OperatorDirective("PREPARE_SITUATION_JOB", next_id)
        return OperatorDirective("RUN_ENGINE_STAGE")
    return OperatorDirective("RUN_ENGINE_STAGE")
