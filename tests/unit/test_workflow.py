from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.workflow import (
    RunState,
    Stage,
    advance,
    lock_situation,
    mark_human_required,
    new_state,
    read_state,
    record_beat_repair,
    record_local_repair,
    record_repair,
    record_stage_metric,
    resume_beat_repair,
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
        state = record_repair(state.run_dir, "SUA_NOI_DUNG", ("UNSUPPORTED_CLAIM",))

    assert state.stage is Stage.CAN_CON_NGUOI_XU_LY
    assert len(read_state(state.run_dir).repair_history) == 3
    with pytest.raises(MvpError, match="human"):
        record_repair(state.run_dir, "SUA_NOI_DUNG", ("UNSUPPORTED_CLAIM",))


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


def test_gemini_ultra_web_phases_are_explicit_workflow_gates(tmp_path: Path) -> None:
    run = tmp_path / "run"
    new_state(run, stage=Stage.VIET_LOI)

    script_wait = advance(run, Stage.VIET_LOI, Stage.CHO_GEMINI_SCRIPT)
    script_done = advance(run, Stage.CHO_GEMINI_SCRIPT, Stage.PHAN_BIEN_KICH_BAN)

    assert script_wait.stage is Stage.CHO_GEMINI_SCRIPT
    assert script_done.stage is Stage.PHAN_BIEN_KICH_BAN

    proxy = replace_state(run, Stage.PHAN_BIEN_VIDEO)
    proxy_wait = advance(run, proxy.stage, Stage.CHO_GEMINI_PROXY)
    proxy_done = advance(run, Stage.CHO_GEMINI_PROXY, Stage.DUNG_VIDEO_CUOI)
    assert proxy_wait.stage is Stage.CHO_GEMINI_PROXY
    assert proxy_done.stage is Stage.DUNG_VIDEO_CUOI


def test_invalid_web_receipt_moves_run_to_human_handling(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run", stage=Stage.CHO_GEMINI_FINAL)

    stopped = mark_human_required(state.run_dir, "GEMINI_WEB_FINAL_VERIFY_FAILED")

    assert stopped.stage is Stage.CAN_CON_NGUOI_XU_LY
    assert stopped.repair_history[-1].phase == "HUMAN"


def replace_state(run: Path, stage: Stage) -> RunState:
    state = read_state(run)
    return new_state(
        run,
        stage=stage,
        episode_dir=Path(state.episode_dir),
        source_video=Path(state.source_video) if state.source_video else None,
    )


def test_content_repair_returns_to_codex_editor(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run", stage=Stage.KIEM_DINH_VIDEO)

    repaired = record_repair(state.run_dir, "SUA_NOI_DUNG", ("SCENE_MISMATCH",))

    assert repaired.stage is Stage.CODEX_BIEN_TAP


def test_antigravity_first_path_does_not_require_codex_editor(tmp_path: Path) -> None:
    path = (
        Stage.CHUAN_BI,
        Stage.QUAN_SAT,
        Stage.LAP_STORYBOARD,
        Stage.VIET_LOI,
        Stage.PHAN_BIEN_KICH_BAN,
        Stage.TAO_TTS,
        Stage.CAN_TTS,
        Stage.DUNG_PROXY,
        Stage.PHAN_BIEN_VIDEO,
        Stage.DUNG_VIDEO_CUOI,
        Stage.KIEM_DINH_ENGINE,
        Stage.HOAN_THANH,
    )

    assert Stage.CODEX_BIEN_TAP not in path
    assert new_state(tmp_path / "run").stage is path[0]


def test_beat_repair_records_only_failed_beats(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run", stage=Stage.PHAN_BIEN_VIDEO)

    repaired = record_beat_repair(
        state.run_dir,
        "VIDEO",
        ("beat-003",),
        ("VOICE_AHEAD",),
    )

    assert repaired.stage is Stage.SUA_BEAT
    assert repaired.repair_history[-1].beat_ids == ("beat-003",)
    assert repaired.repair_history[-1].phase == "VIDEO"


def test_stage_metrics_reject_negative_counters(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run")
    with pytest.raises(MvpError, match="negative"):
        record_stage_metric(state.run_dir, Stage.CHUAN_BI, 1, -1, 0, ())

    measured = record_stage_metric(
        state.run_dir,
        Stage.CHUAN_BI,
        125,
        2,
        1,
        ("beat-001",),
    )
    assert measured.stage_metrics[-1].elapsed_ms == 125
    assert measured.stage_metrics[-1].cache_hits == 2


def test_resume_beat_repair_returns_to_the_smallest_required_stage(tmp_path: Path) -> None:
    state = new_state(tmp_path / "run", stage=Stage.PHAN_BIEN_VIDEO)
    state = record_beat_repair(state.run_dir, "VIDEO", ("beat-001",), ("VOICE_AHEAD",))

    resumed = resume_beat_repair(state.run_dir, "VIDEO")

    assert resumed.stage is Stage.TAO_TTS


def test_local_state_path_has_no_browser_gate(tmp_path: Path) -> None:
    run = tmp_path / "run"
    new_state(run)
    path = (
        (Stage.CHUAN_BI, Stage.QUAN_SAT),
        (Stage.QUAN_SAT, Stage.LAP_TINH_HUONG),
        (Stage.LAP_TINH_HUONG, Stage.VIET_LOI),
        (Stage.VIET_LOI, Stage.TAO_TTS),
        (Stage.TAO_TTS, Stage.CAN_HINH_VOICE),
        (Stage.CAN_HINH_VOICE, Stage.DUNG_PROXY),
        (Stage.DUNG_PROXY, Stage.KIEM_DINH_LOCAL),
        (Stage.KIEM_DINH_LOCAL, Stage.DUNG_VIDEO_CUOI),
        (Stage.DUNG_VIDEO_CUOI, Stage.KIEM_DINH_ENGINE),
    )
    for expected, target in path:
        advance(run, expected, target)

    assert read_state(run).stage is Stage.KIEM_DINH_ENGINE


def test_second_identical_local_repair_stops_no_progress(tmp_path: Path) -> None:
    run = tmp_path / "run"
    new_state(run, stage=Stage.KIEM_DINH_LOCAL)
    first = record_local_repair(
        run,
        ("situation-003",),
        ("VOICE_SCENE_MISMATCH",),
        "a" * 64,
    )
    second = record_local_repair(
        run,
        ("situation-003",),
        ("VOICE_SCENE_MISMATCH",),
        "a" * 64,
    )

    assert first.stage is Stage.VIET_LOI
    assert second.stage is Stage.CAN_CON_NGUOI_XU_LY
    assert second.repair_history[-1].codes == ("KHONG_CO_TIEN_TRIEN",)


def test_lock_situation_records_progress_and_next_unit(tmp_path: Path) -> None:
    run = tmp_path / "run"
    new_state(run, stage=Stage.CAN_HINH_VOICE)

    state = lock_situation(run, "situation-001", next_situation_id="situation-002")

    assert state.locked_situation_ids == ("situation-001",)
    assert state.current_situation_id == "situation-002"


def test_read_state_upgrades_legacy_schema(tmp_path: Path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "run_state.json").write_text(
        '{"run_dir":"'
        + str(run).replace("\\", "\\\\")
        + '","stage":"CHUAN_BI","episode_dir":"","source_video":"",'
        '"repair_history":[],"stage_metrics":[]}',
        encoding="utf-8",
    )

    state = read_state(run)

    assert state.locked_situation_ids == ()
    assert state.current_situation_id == ""
    assert state.last_local_repair_fingerprint == ""
