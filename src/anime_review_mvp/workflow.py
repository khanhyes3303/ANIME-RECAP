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
    CODEX_BIEN_TAP = "CODEX_BIEN_TAP"
    TAO_TTS = "TAO_TTS"
    LAP_EDL = "LAP_EDL"
    DUNG_VIDEO = "DUNG_VIDEO"
    KIEM_DINH_VIDEO = "KIEM_DINH_VIDEO"
    DONG_GOI = "DONG_GOI"
    HOAN_THANH = "HOAN_THANH"
    CAN_CON_NGUOI_XU_LY = "CAN_CON_NGUOI_XU_LY"
    LAP_STORYBOARD = "LAP_STORYBOARD"
    VIET_LOI = "VIET_LOI"
    PHAN_BIEN_KICH_BAN = "PHAN_BIEN_KICH_BAN"
    CAN_TTS = "CAN_TTS"
    DUNG_PROXY = "DUNG_PROXY"
    PHAN_BIEN_VIDEO = "PHAN_BIEN_VIDEO"
    SUA_BEAT = "SUA_BEAT"
    DUNG_VIDEO_CUOI = "DUNG_VIDEO_CUOI"
    KIEM_DINH_ENGINE = "KIEM_DINH_ENGINE"


@dataclass(frozen=True, slots=True)
class RepairRecord:
    owner: str
    codes: tuple[str, ...]
    phase: str = "LEGACY"
    beat_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StageMetric:
    stage: str
    elapsed_ms: int
    cache_hits: int
    cache_misses: int
    changed_beat_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RunState:
    run_dir: Path
    stage: Stage
    episode_dir: str = ""
    source_video: str = ""
    repair_history: tuple[RepairRecord, ...] = ()
    stage_metrics: tuple[StageMetric, ...] = ()


_NEXT_STAGE = {
    Stage.CHUAN_BI: Stage.QUAN_SAT,
    Stage.QUAN_SAT: Stage.LAP_STORYBOARD,
    Stage.LAP_STORYBOARD: Stage.VIET_LOI,
    Stage.VIET_LOI: Stage.PHAN_BIEN_KICH_BAN,
    Stage.PHAN_BIEN_KICH_BAN: Stage.TAO_TTS,
    Stage.TAO_TTS: Stage.CAN_TTS,
    Stage.CAN_TTS: Stage.DUNG_PROXY,
    Stage.DUNG_PROXY: Stage.PHAN_BIEN_VIDEO,
    Stage.PHAN_BIEN_VIDEO: Stage.DUNG_VIDEO_CUOI,
    Stage.DUNG_VIDEO_CUOI: Stage.KIEM_DINH_ENGINE,
    Stage.KIEM_DINH_ENGINE: Stage.HOAN_THANH,
    # Legacy runs already at the old final-audit stage remain resumable.
    Stage.KIEM_DINH_VIDEO: Stage.HOAN_THANH,
}

_LEGACY_TRANSITIONS = {
    (Stage.QUAN_SAT, Stage.VIET_KICH_BAN),
    (Stage.VIET_KICH_BAN, Stage.KIEM_DINH_KICH_BAN),
    (Stage.KIEM_DINH_KICH_BAN, Stage.CODEX_BIEN_TAP),
    (Stage.CODEX_BIEN_TAP, Stage.TAO_TTS),
    (Stage.TAO_TTS, Stage.LAP_EDL),
    (Stage.LAP_EDL, Stage.DUNG_VIDEO),
    (Stage.DUNG_VIDEO, Stage.KIEM_DINH_VIDEO),
}


def _state_path(run_dir: Path) -> Path:
    return run_dir / "run_state.json"


def _write_state(state: RunState) -> None:
    payload = asdict(state)
    payload["run_dir"] = str(state.run_dir)
    payload["stage"] = state.stage.value
    payload["repair_history"] = [
        {
            "owner": record.owner,
            "codes": list(record.codes),
            "phase": record.phase,
            "beat_ids": list(record.beat_ids),
        }
        for record in state.repair_history
    ]
    payload["stage_metrics"] = [
        {
            "stage": metric.stage,
            "elapsed_ms": metric.elapsed_ms,
            "cache_hits": metric.cache_hits,
            "cache_misses": metric.cache_misses,
            "changed_beat_ids": list(metric.changed_beat_ids),
        }
        for metric in state.stage_metrics
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
            "stage_metrics",
        }
        if set(raw) != expected:
            raise MvpError("run state fields do not match the contract")
        return RunState(
            run_dir=Path(raw["run_dir"]),
            stage=Stage(raw["stage"]),
            episode_dir=raw["episode_dir"],
            source_video=raw["source_video"],
            repair_history=tuple(
                RepairRecord(
                    item["owner"],
                    tuple(item["codes"]),
                    item["phase"],
                    tuple(item["beat_ids"]),
                )
                for item in raw["repair_history"]
            ),
            stage_metrics=tuple(
                StageMetric(
                    item["stage"],
                    item["elapsed_ms"],
                    item["cache_hits"],
                    item["cache_misses"],
                    tuple(item["changed_beat_ids"]),
                )
                for item in raw["stage_metrics"]
            ),
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise MvpError(f"cannot read run state: {run_dir}") from exc


def advance(
    run_dir: Path,
    expected: Stage,
    target: Stage,
    *,
    _engine_audit_passed: bool = False,
) -> RunState:
    state = read_state(run_dir)
    if state.stage is not expected:
        raise MvpError(
            f"persisted stage is {state.stage}; expected {expected} before advancing"
        )
    if _NEXT_STAGE.get(expected) is not target and (expected, target) not in _LEGACY_TRANSITIONS:
        raise MvpError(f"forbidden workflow transition: {expected} -> {target}")
    if target is Stage.HOAN_THANH and not _engine_audit_passed:
        raise MvpError("only a successful engine audit may mark a run complete")
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
        target = Stage.CODEX_BIEN_TAP if owner == "SUA_NOI_DUNG" else Stage.LAP_EDL
    state = replace(state, stage=target, repair_history=history)
    _write_state(state)
    return state


def record_beat_repair(
    run_dir: Path,
    phase: str,
    beat_ids: tuple[str, ...],
    codes: tuple[str, ...],
) -> RunState:
    state = read_state(run_dir)
    if state.stage in {Stage.HOAN_THANH, Stage.CAN_CON_NGUOI_XU_LY}:
        raise MvpError("run already requires human handling or is complete")
    if phase not in {"SCRIPT", "TTS", "VIDEO"} or not beat_ids or not codes:
        raise MvpError("beat repair requires phase, beat IDs, and codes")
    history = (*state.repair_history, RepairRecord("ANTIGRAVITY", codes, phase, beat_ids))
    target = Stage.CAN_CON_NGUOI_XU_LY if len(history) >= 3 else Stage.SUA_BEAT
    state = replace(state, stage=target, repair_history=history)
    _write_state(state)
    return state


def record_stage_metric(
    run_dir: Path,
    stage: Stage,
    elapsed_ms: int,
    cache_hits: int,
    cache_misses: int,
    changed_beat_ids: tuple[str, ...],
) -> RunState:
    if min(elapsed_ms, cache_hits, cache_misses) < 0:
        raise MvpError("stage metrics cannot contain negative values")
    state = read_state(run_dir)
    metric = StageMetric(
        stage.value,
        elapsed_ms,
        cache_hits,
        cache_misses,
        changed_beat_ids,
    )
    state = replace(state, stage_metrics=(*state.stage_metrics, metric))
    _write_state(state)
    return state
