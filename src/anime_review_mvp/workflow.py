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
    CHO_GEMINI_SCRIPT = "CHO_GEMINI_SCRIPT"
    PHAN_BIEN_KICH_BAN = "PHAN_BIEN_KICH_BAN"
    CAN_TTS = "CAN_TTS"
    DUNG_PROXY = "DUNG_PROXY"
    PHAN_BIEN_VIDEO = "PHAN_BIEN_VIDEO"
    CHO_GEMINI_PROXY = "CHO_GEMINI_PROXY"
    SUA_BEAT = "SUA_BEAT"
    DUNG_VIDEO_CUOI = "DUNG_VIDEO_CUOI"
    CHO_GEMINI_FINAL = "CHO_GEMINI_FINAL"
    KIEM_DINH_ENGINE = "KIEM_DINH_ENGINE"
    LAP_TINH_HUONG = "LAP_TINH_HUONG"
    CAN_HINH_VOICE = "CAN_HINH_VOICE"
    KIEM_DINH_LOCAL = "KIEM_DINH_LOCAL"
    TRICH_XUAT_BANG_CHUNG = "TRICH_XUAT_BANG_CHUNG"
    CHO_ANTIGRAVITY_TINH_HUONG = "CHO_ANTIGRAVITY_TINH_HUONG"
    KIEM_DINH_TINH_HUONG = "KIEM_DINH_TINH_HUONG"
    TAO_TTS_TINH_HUONG = "TAO_TTS_TINH_HUONG"
    LAP_TIMELINE_TINH_HUONG = "LAP_TIMELINE_TINH_HUONG"
    KIEM_DINH_NGU_NGHIA_TINH_HUONG = "KIEM_DINH_NGU_NGHIA_TINH_HUONG"
    KIEM_DINH_MACH_TRUYEN_TOAN_TAP = "KIEM_DINH_MACH_TRUYEN_TOAN_TAP"
    KIEM_DINH_PROXY = "KIEM_DINH_PROXY"
    CHO_NGUOI_DUNG_DUYET_PROXY = "CHO_NGUOI_DUNG_DUYET_PROXY"


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
    locked_situation_ids: tuple[str, ...] = ()
    current_situation_id: str = ""
    last_local_repair_fingerprint: str = ""
    last_local_repair_codes: tuple[str, ...] = ()
    editor_task_id: str = ""
    editorial_revision: int = 0
    approved_proxy_sha256: str = ""
    approved_artifact_sha256: str = ""
    proxy_rejection_note: str = ""


_NEXT_STAGE = {
    Stage.CHUAN_BI: Stage.QUAN_SAT,
    Stage.QUAN_SAT: Stage.LAP_TINH_HUONG,
    Stage.LAP_TINH_HUONG: Stage.VIET_LOI,
    Stage.VIET_LOI: Stage.TAO_TTS,
    Stage.CHO_GEMINI_SCRIPT: Stage.PHAN_BIEN_KICH_BAN,
    Stage.PHAN_BIEN_KICH_BAN: Stage.TAO_TTS,
    Stage.TAO_TTS: Stage.CAN_HINH_VOICE,
    Stage.CAN_HINH_VOICE: Stage.DUNG_PROXY,
    Stage.DUNG_PROXY: Stage.KIEM_DINH_LOCAL,
    Stage.KIEM_DINH_LOCAL: Stage.DUNG_VIDEO_CUOI,
    Stage.PHAN_BIEN_VIDEO: Stage.CHO_GEMINI_PROXY,
    Stage.CHO_GEMINI_PROXY: Stage.DUNG_VIDEO_CUOI,
    Stage.DUNG_VIDEO_CUOI: Stage.KIEM_DINH_ENGINE,
    Stage.CHO_GEMINI_FINAL: Stage.KIEM_DINH_ENGINE,
    Stage.KIEM_DINH_ENGINE: Stage.HOAN_THANH,
    # Legacy runs already at the old final-audit stage remain resumable.
    Stage.KIEM_DINH_VIDEO: Stage.HOAN_THANH,
}

_LEGACY_TRANSITIONS = {
    (Stage.QUAN_SAT, Stage.LAP_STORYBOARD),
    (Stage.LAP_TINH_HUONG, Stage.LAP_STORYBOARD),
    (Stage.LAP_STORYBOARD, Stage.VIET_LOI),
    (Stage.VIET_LOI, Stage.CHO_GEMINI_SCRIPT),
    (Stage.TAO_TTS, Stage.CAN_TTS),
    (Stage.CAN_TTS, Stage.DUNG_PROXY),
    (Stage.DUNG_PROXY, Stage.PHAN_BIEN_VIDEO),
    (Stage.DUNG_VIDEO_CUOI, Stage.CHO_GEMINI_FINAL),
    (Stage.QUAN_SAT, Stage.VIET_KICH_BAN),
    (Stage.VIET_KICH_BAN, Stage.KIEM_DINH_KICH_BAN),
    (Stage.KIEM_DINH_KICH_BAN, Stage.CODEX_BIEN_TAP),
    (Stage.CODEX_BIEN_TAP, Stage.TAO_TTS),
    (Stage.TAO_TTS, Stage.LAP_EDL),
    (Stage.LAP_EDL, Stage.DUNG_VIDEO),
    (Stage.DUNG_VIDEO, Stage.KIEM_DINH_VIDEO),
}

_V2_TRANSITIONS = {
    (Stage.CHUAN_BI, Stage.TRICH_XUAT_BANG_CHUNG),
    (Stage.TRICH_XUAT_BANG_CHUNG, Stage.CHO_ANTIGRAVITY_TINH_HUONG),
    (Stage.CHO_ANTIGRAVITY_TINH_HUONG, Stage.KIEM_DINH_TINH_HUONG),
    (Stage.KIEM_DINH_TINH_HUONG, Stage.TAO_TTS_TINH_HUONG),
    (Stage.TAO_TTS_TINH_HUONG, Stage.LAP_TIMELINE_TINH_HUONG),
    (Stage.LAP_TIMELINE_TINH_HUONG, Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG),
    (Stage.KIEM_DINH_MACH_TRUYEN_TOAN_TAP, Stage.DUNG_PROXY),
    (Stage.DUNG_PROXY, Stage.KIEM_DINH_PROXY),
    (Stage.KIEM_DINH_PROXY, Stage.CHO_NGUOI_DUNG_DUYET_PROXY),
    (Stage.CHO_NGUOI_DUNG_DUYET_PROXY, Stage.DUNG_VIDEO_CUOI),
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
    payload["locked_situation_ids"] = list(state.locked_situation_ids)
    payload["last_local_repair_codes"] = list(state.last_local_repair_codes)
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
        legacy_fields = {
            "run_dir",
            "stage",
            "episode_dir",
            "source_video",
            "repair_history",
            "stage_metrics",
        }
        current_fields = {
            *legacy_fields,
            "locked_situation_ids",
            "current_situation_id",
            "last_local_repair_fingerprint",
            "last_local_repair_codes",
        }
        v2_fields = {
            *current_fields,
            "editor_task_id",
            "editorial_revision",
            "approved_proxy_sha256",
            "approved_artifact_sha256",
            "proxy_rejection_note",
        }
        if frozenset(raw) not in {
            frozenset(legacy_fields), frozenset(current_fields), frozenset(v2_fields)
        }:
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
            locked_situation_ids=tuple(raw.get("locked_situation_ids", ())),
            current_situation_id=raw.get("current_situation_id", ""),
            last_local_repair_fingerprint=raw.get("last_local_repair_fingerprint", ""),
            last_local_repair_codes=tuple(raw.get("last_local_repair_codes", ())),
            editor_task_id=raw.get("editor_task_id", ""),
            editorial_revision=raw.get("editorial_revision", 0),
            approved_proxy_sha256=raw.get("approved_proxy_sha256", ""),
            approved_artifact_sha256=raw.get("approved_artifact_sha256", ""),
            proxy_rejection_note=raw.get("proxy_rejection_note", ""),
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise MvpError(f"cannot read run state: {run_dir}") from exc


def advance(
    run_dir: Path,
    expected: Stage,
    target: Stage,
    *,
    _engine_audit_passed: bool = False,
    _proxy_approval_verified: bool = False,
) -> RunState:
    state = read_state(run_dir)
    if state.stage is not expected:
        raise MvpError(f"persisted stage is {state.stage}; expected {expected} before advancing")
    if (
        _NEXT_STAGE.get(expected) is not target
        and (expected, target) not in _LEGACY_TRANSITIONS
        and (expected, target) not in _V2_TRANSITIONS
    ):
        raise MvpError(f"forbidden workflow transition: {expected} -> {target}")
    if (
        expected is Stage.CHO_NGUOI_DUNG_DUYET_PROXY
        and target is Stage.DUNG_VIDEO_CUOI
        and not _proxy_approval_verified
    ):
        raise MvpError("explicit proxy approval is required before final render")
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


def lock_situation(
    run_dir: Path,
    situation_id: str,
    *,
    next_situation_id: str = "",
) -> RunState:
    normalized = situation_id.strip()
    if not normalized:
        raise MvpError("situation ID is required before locking")
    state = read_state(run_dir)
    if state.stage is not Stage.CAN_HINH_VOICE:
        raise MvpError("situation can only lock after image/voice alignment")
    if normalized in state.locked_situation_ids:
        raise MvpError("situation is already locked")
    state = replace(
        state,
        locked_situation_ids=(*state.locked_situation_ids, normalized),
        current_situation_id=next_situation_id.strip(),
    )
    _write_state(state)
    return state


def lock_editor_situation(
    run_dir: Path,
    situation_id: str,
    *,
    next_situation_id: str = "",
) -> RunState:
    state = read_state(run_dir)
    normalized = situation_id.strip()
    if state.stage is not Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG:
        raise MvpError("editor situation can only lock after semantic validation")
    if not normalized or normalized in state.locked_situation_ids:
        raise MvpError("editor situation ID is missing or already locked")
    following = next_situation_id.strip()
    state = replace(
        state,
        stage=(
            Stage.CHO_ANTIGRAVITY_TINH_HUONG
            if following
            else Stage.KIEM_DINH_MACH_TRUYEN_TOAN_TAP
        ),
        locked_situation_ids=(*state.locked_situation_ids, normalized),
        current_situation_id=following,
        editor_task_id="",
    )
    _write_state(state)
    return state


def begin_editor_task(
    run_dir: Path,
    task_id: str,
    situation_id: str,
    revision: int,
) -> RunState:
    state = read_state(run_dir)
    if state.stage is not Stage.CHO_ANTIGRAVITY_TINH_HUONG:
        raise MvpError("editor task can only begin at the Antigravity wait stage")
    if not task_id.strip() or not situation_id.strip() or revision < 1:
        raise MvpError("editor task ID, situation ID, and revision are required")
    state = replace(
        state,
        editor_task_id=task_id.strip(),
        current_situation_id=situation_id.strip(),
        editorial_revision=revision,
    )
    _write_state(state)
    return state


def accept_editor_revision(
    run_dir: Path,
    task_id: str,
    revision: int,
) -> RunState:
    state = read_state(run_dir)
    if state.stage is not Stage.CHO_ANTIGRAVITY_TINH_HUONG:
        raise MvpError("editor revision can only be accepted from the Antigravity stage")
    if state.editor_task_id != task_id or state.editorial_revision != revision:
        raise MvpError("accepted editor revision does not match the active task")
    state = replace(state, stage=Stage.KIEM_DINH_TINH_HUONG)
    _write_state(state)
    return state


def route_editor_repair(
    run_dir: Path,
    situation_ids: tuple[str, ...],
    codes: tuple[str, ...],
    fingerprint: str,
) -> RunState:
    state = read_state(run_dir)
    if not situation_ids or not codes:
        raise MvpError("editor repair requires situation IDs and codes")
    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
        raise MvpError("editor repair fingerprint must be a lowercase SHA-256")
    history = (
        *state.repair_history,
        RepairRecord("ANTIGRAVITY", codes, "SITUATION", situation_ids),
    )
    if (
        state.last_local_repair_fingerprint == fingerprint
        and state.last_local_repair_codes == codes
    ):
        state = replace(
            state,
            stage=Stage.CAN_CON_NGUOI_XU_LY,
            repair_history=history,
        )
    else:
        state = replace(
            state,
            stage=Stage.CHO_ANTIGRAVITY_TINH_HUONG,
            repair_history=history,
            current_situation_id=situation_ids[0],
            last_local_repair_fingerprint=fingerprint,
            last_local_repair_codes=codes,
            editor_task_id="",
        )
    _write_state(state)
    return state


def approve_proxy_state(
    run_dir: Path, proxy_sha256: str, artifact_sha256: str
) -> RunState:
    state = advance(
        run_dir,
        Stage.CHO_NGUOI_DUNG_DUYET_PROXY,
        Stage.DUNG_VIDEO_CUOI,
        _proxy_approval_verified=True,
    )
    state = replace(
        state,
        approved_proxy_sha256=proxy_sha256,
        approved_artifact_sha256=artifact_sha256,
        proxy_rejection_note="",
    )
    _write_state(state)
    return state


def reject_proxy_state(
    run_dir: Path, note: str, situation_ids: tuple[str, ...]
) -> RunState:
    state = read_state(run_dir)
    if state.stage is not Stage.CHO_NGUOI_DUNG_DUYET_PROXY:
        raise MvpError("proxy can only be rejected while awaiting user approval")
    if not note.strip() or not situation_ids:
        raise MvpError("proxy rejection requires a note and situation IDs")
    history = (
        *state.repair_history,
        RepairRecord("ANTIGRAVITY", ("USER_REJECTED_PROXY",), "PROXY", situation_ids),
    )
    state = replace(
        state,
        stage=Stage.CHO_ANTIGRAVITY_TINH_HUONG,
        repair_history=history,
        current_situation_id=situation_ids[0],
        proxy_rejection_note=note.strip(),
        approved_proxy_sha256="",
        approved_artifact_sha256="",
        editor_task_id="",
    )
    _write_state(state)
    return state


def record_local_repair(
    run_dir: Path,
    situation_ids: tuple[str, ...],
    codes: tuple[str, ...],
    fingerprint: str,
) -> RunState:
    state = read_state(run_dir)
    if state.stage in {Stage.HOAN_THANH, Stage.CAN_CON_NGUOI_XU_LY}:
        raise MvpError("run already requires human handling or is complete")
    if not situation_ids or not codes:
        raise MvpError("local repair requires situation IDs and finding codes")
    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdef" for character in fingerprint
    ):
        raise MvpError("local repair fingerprint must be a lowercase SHA-256")
    if (
        state.last_local_repair_fingerprint == fingerprint
        and state.last_local_repair_codes == codes
    ):
        history = (
            *state.repair_history,
            RepairRecord(
                "LOCAL_EDITOR",
                ("KHONG_CO_TIEN_TRIEN",),
                "LOCAL",
                situation_ids,
            ),
        )
        state = replace(state, stage=Stage.CAN_CON_NGUOI_XU_LY, repair_history=history)
    else:
        history = (
            *state.repair_history,
            RepairRecord("LOCAL_EDITOR", codes, "LOCAL", situation_ids),
        )
        state = replace(
            state,
            stage=Stage.VIET_LOI,
            repair_history=history,
            current_situation_id=situation_ids[0],
            last_local_repair_fingerprint=fingerprint,
            last_local_repair_codes=codes,
        )
    _write_state(state)
    return state


def mark_human_required(run_dir: Path, code: str) -> RunState:
    normalized = code.strip()
    if not normalized:
        raise MvpError("human-handling code is required")
    state = read_state(run_dir)
    if state.stage is Stage.HOAN_THANH:
        raise MvpError("completed run cannot be moved to human handling")
    if state.stage is Stage.CAN_CON_NGUOI_XU_LY:
        return state
    history = (*state.repair_history, RepairRecord("ANTIGRAVITY", (code,), "HUMAN"))
    state = replace(state, stage=Stage.CAN_CON_NGUOI_XU_LY, repair_history=history)
    _write_state(state)
    return state


def resume_browser_review(run_dir: Path, phase: str) -> RunState:
    state = read_state(run_dir)
    if state.stage is not Stage.CAN_CON_NGUOI_XU_LY:
        raise MvpError("only a browser review stopped for human handling can resume")
    target_by_phase = {
        "SCRIPT": Stage.CHO_GEMINI_SCRIPT,
        "PROXY": Stage.CHO_GEMINI_PROXY,
        "FINAL": Stage.CHO_GEMINI_FINAL,
    }
    try:
        target = target_by_phase[phase.upper()]
    except KeyError as exc:
        raise MvpError("browser review phase is invalid") from exc
    state = replace(state, stage=target)
    _write_state(state)
    return state


def resume_beat_repair(run_dir: Path, phase: str) -> RunState:
    state = read_state(run_dir)
    if state.stage is not Stage.SUA_BEAT or not state.repair_history:
        raise MvpError("only a pending beat repair can resume")
    if phase not in {"SCRIPT", "TTS", "VIDEO"}:
        raise MvpError("repair phase is invalid")
    if state.repair_history[-1].phase != phase:
        raise MvpError("repair phase does not match the latest finding")
    target = Stage.VIET_LOI if phase == "SCRIPT" else Stage.TAO_TTS
    state = replace(state, stage=target)
    _write_state(state)
    return state
