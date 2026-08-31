from __future__ import annotations

import json
from pathlib import Path

from anime_review_mvp import cli
from anime_review_mvp.editor_provenance import (
    accept_antigravity_submission,
    create_editor_task,
)
from anime_review_mvp.workflow import (
    Stage,
    accept_editor_revision,
    accept_structure_index,
    advance,
    begin_editor_task,
    lock_editor_situation,
    new_state,
    read_state,
)


def test_simplified_pipeline_reaches_proxy_gate_without_external_services(
    tmp_path: Path,
) -> None:
    run = tmp_path / "run"
    new_state(run)

    advance(run, Stage.CHUAN_BI, Stage.TRICH_XUAT_BANG_CHUNG)
    advance(run, Stage.TRICH_XUAT_BANG_CHUNG, Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG)
    advance(
        run,
        Stage.CHO_ANTIGRAVITY_CHIA_TINH_HUONG,
        Stage.KIEM_DINH_CHI_MUC_TINH_HUONG,
    )
    accept_structure_index(run, "a" * 64, "situation-001")

    transcript = run / "transcript.json"
    frames = run / "frames.json"
    transcript.write_text('{"text":"Jiro về nhà"}', encoding="utf-8")
    frames.write_text('{"shots":["shot-001"]}', encoding="utf-8")
    task = create_editor_task(run, "run-001", "situation-001", 1, (transcript, frames))
    begin_editor_task(run, task.task_id, task.situation_id, task.revision)
    staging = run / "editor_staging" / task.task_id
    staging.mkdir(parents=True)
    situation = staging / "situation_draft.json"
    narration = staging / "narration_draft.json"
    situation.write_text('{"situation_id":"situation-001"}', encoding="utf-8")
    narration.write_text('{"cue_id":"cue-001"}', encoding="utf-8")
    accepted = accept_antigravity_submission(run, task.task_id, staging)
    accept_editor_revision(run, task.task_id, accepted.revision)

    transitions = (
        (Stage.KIEM_DINH_TINH_HUONG, Stage.TAO_TTS_TINH_HUONG),
        (Stage.TAO_TTS_TINH_HUONG, Stage.LAP_TIMELINE_TINH_HUONG),
        (Stage.LAP_TIMELINE_TINH_HUONG, Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG),
        (
            Stage.KIEM_DINH_NGU_NGHIA_TINH_HUONG,
            Stage.CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG,
        ),
        (
            Stage.CHO_ANTIGRAVITY_KIEM_DINH_TINH_HUONG,
            Stage.KIEM_DINH_PHAN_BIEN_TINH_HUONG,
        ),
    )
    for current, following in transitions:
        advance(run, current, following)

    lock_editor_situation(run, "situation-001")
    for current, following in (
        (Stage.KIEM_DINH_MACH_TRUYEN_TOAN_TAP, Stage.DUNG_PROXY),
        (Stage.DUNG_PROXY, Stage.KIEM_DINH_PROXY),
        (Stage.KIEM_DINH_PROXY, Stage.CHO_ANTIGRAVITY_KIEM_DINH_PROXY),
        (
            Stage.CHO_ANTIGRAVITY_KIEM_DINH_PROXY,
            Stage.KIEM_DINH_PHAN_BIEN_PROXY,
        ),
        (Stage.KIEM_DINH_PHAN_BIEN_PROXY, Stage.CHO_NGUOI_DUNG_DUYET_PROXY),
    ):
        advance(run, current, following)

    cli._write_next(run, "Người dùng xem proxy rồi approve hoặc reject.")
    status = json.loads((run / "next_action.json").read_text(encoding="utf-8"))

    assert read_state(run).stage is Stage.CHO_NGUOI_DUNG_DUYET_PROXY
    assert status["public_stage"] == "CHO_NGUOI_DUNG_DUYET_PROXY"
    assert not (run / "tts").exists()
    assert not (run / "proxy" / "review_proxy.mp4").exists()
