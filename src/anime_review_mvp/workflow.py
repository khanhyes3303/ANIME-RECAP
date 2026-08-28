from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
from pathlib import Path

from .errors import MvpError


class Stage(StrEnum):
    CHUAN_BI = "CHUAN_BI"
    QUAN_SAT = "QUAN_SAT"
    VIET_KICH_BAN = "VIET_KICH_BAN"
    KIEM_DINH_KICH_BAN = "KIEM_DINH_KICH_BAN"
    TAO_TTS = "TAO_TTS"
    LAP_EDL = "LAP_EDL"
    DUNG_VIDEO = "DUNG_VIDEO"
    KIEM_DINH_VIDEO = "KIEM_DINH_VIDEO"
    DONG_GOI = "DONG_GOI"
    HOAN_THANH = "HOAN_THANH"
    CAN_CON_NGUOI_XU_LY = "CAN_CON_NGUOI_XU_LY"


@dataclass(frozen=True, slots=True)
class RepairRecord:
    owner: str
    codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunState:
    run_dir: Path
    stage: Stage
    episode_dir: str = ""
    source_video: str = ""
    repair_history: tuple[RepairRecord, ...] = ()


_NEXT_STAGE = {
    Stage.CHUAN_BI: Stage.QUAN_SAT,
    Stage.QUAN_SAT: Stage.VIET_KICH_BAN,
    Stage.VIET_KICH_BAN: Stage.KIEM_DINH_KICH_BAN,
    Stage.KIEM_DINH_KICH_BAN: Stage.TAO_TTS,
    Stage.TAO_TTS: Stage.LAP_EDL,
    Stage.LAP_EDL: Stage.DUNG_VIDEO,
    Stage.DUNG_VIDEO: Stage.KIEM_DINH_VIDEO,
    Stage.KIEM_DINH_VIDEO: Stage.DONG_GOI,
    Stage.DONG_GOI: Stage.HOAN_THANH,
}


def _state_path(run_dir: Path) -> Path:
    return run_dir / "run_state.json"


def _write_state(state: RunState) -> None:
    payload = asdict(state)
    payload["run_dir"] = str(state.run_dir)
    payload["stage"] = state.stage.value
    payload["repair_history"] = [
        {"owner": record.owner, "codes": list(record.codes)}
        for record in state.repair_history
    ]
    _state_path(state.run_dir).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def new_state(
    run_dir: Path,
    *,
    stage: Stage = Stage.CHUAN_BI,
    episode_dir: Path | None = None,
    source_video: Path | None = None,
) -> RunState:
    run_dir.mkdir(parents=True, exist_ok=True)
    state = RunState(
        run_dir=run_dir.resolve(),
        stage=stage,
        episode_dir=str(episode_dir.resolve()) if episode_dir else "",
        source_video=str(source_video.resolve()) if source_video else "",
    )
    _write_state(state)
    return state


def read_state(run_dir: Path) -> RunState:
    try:
        raw = json.loads(_state_path(run_dir).read_text(encoding="utf-8"))
        expected = {
            "run_dir",
            "stage",
            "episode_dir",
            "source_video",
            "repair_history",
        }
        if set(raw) != expected:
            raise MvpError("run state fields do not match the contract")
        return RunState(
            run_dir=Path(raw["run_dir"]),
            stage=Stage(raw["stage"]),
            episode_dir=raw["episode_dir"],
            source_video=raw["source_video"],
            repair_history=tuple(
                RepairRecord(item["owner"], tuple(item["codes"]))
                for item in raw["repair_history"]
            ),
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise MvpError(f"cannot read run state: {run_dir}") from exc


def advance(
    run_dir: Path,
    expected: Stage,
    target: Stage,
    *,
    _package_completed: bool = False,
) -> RunState:
    state = read_state(run_dir)
    if state.stage is not expected:
        raise MvpError(
            f"persisted stage is {state.stage}; expected {expected} before advancing"
        )
    if _NEXT_STAGE.get(expected) is not target:
        raise MvpError(f"forbidden workflow transition: {expected} -> {target}")
    if target is Stage.HOAN_THANH and not _package_completed:
        raise MvpError("only successful package finalization may mark a run complete")
    state = replace(state, stage=target)
    _write_state(state)
    return state


def record_repair(run_dir: Path, owner: str, codes: tuple[str, ...]) -> RunState:
    state = read_state(run_dir)
    if state.stage in {Stage.HOAN_THANH, Stage.CAN_CON_NGUOI_XU_LY}:
        raise MvpError("run already requires human handling or is complete")
    if owner not in {"SUA_NOI_DUNG", "SUA_EDL"} or not codes:
        raise MvpError("repair owner and codes are required")
    history = (*state.repair_history, RepairRecord(owner, codes))
    if len(history) >= 3:
        target = Stage.CAN_CON_NGUOI_XU_LY
    else:
        target = Stage.VIET_KICH_BAN if owner == "SUA_NOI_DUNG" else Stage.LAP_EDL
    state = replace(state, stage=target, repair_history=history)
    _write_state(state)
    return state
