from __future__ import annotations

import json
from pathlib import Path

import pytest

from anime_review_mvp.editor_provenance import (
    AcceptedVerifierRevision,
    accept_antigravity_submission,
    create_editor_task,
    load_editor_ledger,
    load_editor_task,
    load_verifier_ledger,
    require_antigravity_provenance,
    validate_task_inputs,
    validate_task_submission,
)
from anime_review_mvp.errors import MvpError
from anime_review_mvp.jsonio import atomic_append_jsonl


def _prepared_submission(
    tmp_path: Path,
) -> tuple[Path, tuple[Path, ...], str, Path]:
    run = tmp_path / "run"
    transcript = tmp_path / "transcript.json"
    frames = tmp_path / "frames.json"
    transcript.write_text('{"text":"Jiro returns"}', encoding="utf-8")
    frames.write_text('{"shots":["shot-001"]}', encoding="utf-8")
    inputs = (transcript, frames)
    task = create_editor_task(run, "run-001", "situation-001", 1, inputs)
    staging = run / "editor_staging" / task.task_id
    staging.mkdir(parents=True)
    (staging / "situation_draft.json").write_text(
        '{"situation_id":"situation-001"}', encoding="utf-8"
    )
    (staging / "narration_draft.json").write_text(
        '{"owner":"CODEX","situation_id":"situation-001"}', encoding="utf-8"
    )
    return run, inputs, task.task_id, staging


def test_accept_antigravity_submission_records_engine_owned_provenance(
    tmp_path: Path,
) -> None:
    run, _inputs, task_id, staging = _prepared_submission(tmp_path)

    accepted = accept_antigravity_submission(run, task_id, staging)

    assert accepted.actor == "ANTIGRAVITY"
    assert accepted.task_id == task_id
    assert accepted.revision == 1
    assert len(load_editor_ledger(run / "editor_ledger.jsonl")) == 1
    accepted_dir = run / "accepted_editorial" / "situation-001" / "revision-001"
    assert json.loads(
        (accepted_dir / "narration_draft.json").read_text(encoding="utf-8")
    )["owner"] == "CODEX"


def test_legacy_editor_task_without_kind_loads_as_situation(tmp_path: Path) -> None:
    task_path = tmp_path / "task.json"
    task_path.write_text(
        '{"task_id":"situation-001-revision-001","run_id":"run-001",'
        '"situation_id":"situation-001","revision":1,'
        '"expected_stage":"ANTIGRAVITY_EDITORIAL","input_paths":["a.json"],'
        '"input_sha256":"' + "a" * 64 + '",'
        '"allowed_outputs":["situation_draft.json","narration_draft.json"]}',
        encoding="utf-8",
    )

    task = load_editor_task(task_path)

    assert task.task_kind == "SITUATION"


def test_editor_task_accepts_verifier_task_kinds(tmp_path: Path) -> None:
    task_path = tmp_path / "task.json"
    task_path.write_text(
        '{"task_id":"situation-001-audit-001","run_id":"run-001",'
        '"situation_id":"situation-001","revision":1,'
        '"expected_stage":"ANTIGRAVITY_VERIFIER","input_paths":["a.json"],'
        '"input_sha256":"' + "a" * 64 + '",'
        '"allowed_outputs":["situation_audit_draft.json"],'
        '"task_kind":"SITUATION_AUDIT"}',
        encoding="utf-8",
    )

    task = load_editor_task(task_path)

    assert task.task_kind == "SITUATION_AUDIT"


def test_load_verifier_ledger_round_trips_records(tmp_path: Path) -> None:
    ledger_path = tmp_path / "verifier_ledger.jsonl"
    record = AcceptedVerifierRevision(
        task_id="situation-001-audit-001",
        run_id="run-001",
        task_kind="SITUATION_AUDIT",
        situation_id="situation-001",
        revision=1,
        actor="ANTIGRAVITY_VERIFIER",
        input_sha256="a" * 64,
        audit_sha256="b" * 64,
    )
    atomic_append_jsonl(ledger_path, record)

    assert load_verifier_ledger(ledger_path) == (record,)


def test_accept_rejects_changed_editor_inputs(tmp_path: Path) -> None:
    run, inputs, task_id, staging = _prepared_submission(tmp_path)
    inputs[0].write_text('{"text":"changed"}', encoding="utf-8")

    with pytest.raises(MvpError, match="EDITOR_INPUT_HASH_CHANGED"):
        accept_antigravity_submission(run, task_id, staging)


def test_verifier_validation_rejects_changed_inputs(tmp_path: Path) -> None:
    run = tmp_path / "run"
    source = tmp_path / "narration_plan.json"
    source.write_text('{"revision":1}', encoding="utf-8")
    task = create_editor_task(
        run,
        "run-001",
        "situation-001",
        1,
        (source,),
        task_kind="SITUATION_AUDIT",
        task_id="situation-001-audit-revision-001",
        allowed_outputs=("situation_audit_draft.json",),
    )
    source.write_text('{"revision":2}', encoding="utf-8")

    with pytest.raises(MvpError, match="EDITOR_INPUT_HASH_CHANGED"):
        validate_task_inputs(task)


def test_task_validation_rejects_changed_engine_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = tmp_path / "run"
    source = tmp_path / "input.json"
    source.write_text("{}", encoding="utf-8")
    task = create_editor_task(run, "run-001", "situation-001", 1, (source,))
    monkeypatch.setattr(
        "anime_review_mvp.antigravity.calculate_policy_sha256",
        lambda _root: "f" * 64,
    )

    with pytest.raises(MvpError, match="EDITOR_POLICY_HASH_CHANGED"):
        validate_task_inputs(task)


def test_verifier_submission_requires_isolated_exact_output(tmp_path: Path) -> None:
    run = tmp_path / "run"
    source = tmp_path / "input.json"
    source.write_text("{}", encoding="utf-8")
    task = create_editor_task(
        run,
        "run-001",
        "situation-001",
        1,
        (source,),
        task_kind="SITUATION_AUDIT",
        task_id="situation-001-audit-revision-001",
        allowed_outputs=("situation_audit_draft.json",),
    )
    staging = run / "verifier_staging" / task.task_id
    staging.mkdir(parents=True)
    (staging / "situation_audit_draft.json").write_text("{}", encoding="utf-8")
    (staging / "producer-draft.json").write_text("{}", encoding="utf-8")

    with pytest.raises(MvpError, match="EDITOR_SUBMISSION_INVALID"):
        validate_task_submission(run, task, staging, staging_root="verifier_staging")


def test_accept_rejects_stale_revision_for_same_situation(tmp_path: Path) -> None:
    run, inputs, task_id, staging = _prepared_submission(tmp_path)
    accept_antigravity_submission(run, task_id, staging)
    stale = create_editor_task(run, "run-001", "situation-001", 1, inputs)
    stale_staging = run / "editor_staging" / stale.task_id
    stale_staging.mkdir(parents=True, exist_ok=True)
    (stale_staging / "situation_draft.json").write_text("{}", encoding="utf-8")
    (stale_staging / "narration_draft.json").write_text("{}", encoding="utf-8")

    with pytest.raises(MvpError, match="EDITOR_REVISION_STALE"):
        accept_antigravity_submission(run, stale.task_id, stale_staging)


def test_require_provenance_matches_accepted_artifact_hashes(tmp_path: Path) -> None:
    run, _inputs, task_id, staging = _prepared_submission(tmp_path)
    accepted = accept_antigravity_submission(run, task_id, staging)
    accepted_dir = run / "accepted_editorial" / "situation-001" / "revision-001"

    verified = require_antigravity_provenance(
        run,
        "situation-001",
        (
            accepted_dir / "situation_draft.json",
            accepted_dir / "narration_draft.json",
        ),
    )

    assert verified == accepted


def test_require_provenance_rejects_artifact_changed_after_acceptance(
    tmp_path: Path,
) -> None:
    run, _inputs, task_id, staging = _prepared_submission(tmp_path)
    accept_antigravity_submission(run, task_id, staging)
    accepted_dir = run / "accepted_editorial" / "situation-001" / "revision-001"
    narration = accepted_dir / "narration_draft.json"
    narration.write_text('{"changed":true}', encoding="utf-8")

    with pytest.raises(MvpError, match="EDITOR_PROVENANCE_INVALID"):
        require_antigravity_provenance(
            run,
            "situation-001",
            (accepted_dir / "situation_draft.json", narration),
        )
