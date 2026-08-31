from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .errors import MvpError
from .jsonio import atomic_append_jsonl, atomic_dump_json, load_json

_EDITOR_TASK_KINDS = {"STRUCTURE", "SITUATION", "SITUATION_AUDIT", "PROXY_AUDIT"}


@dataclass(frozen=True)
class EditorTask:
    task_id: str
    run_id: str
    situation_id: str
    revision: int
    expected_stage: str
    input_paths: tuple[str, ...]
    input_sha256: str
    allowed_outputs: tuple[str, ...]
    task_kind: str = field(default="SITUATION", metadata={"json_optional": True})
    policy_sha256: str = field(default="", metadata={"json_optional": True})

    def __post_init__(self) -> None:
        if self.task_kind not in _EDITOR_TASK_KINDS:
            raise MvpError("EDITOR_TASK_INVALID")


@dataclass(frozen=True)
class AcceptedEditorialRevision:
    task_id: str
    run_id: str
    situation_id: str
    revision: int
    actor: str
    input_sha256: str
    situation_sha256: str
    narration_sha256: str
    policy_sha256: str = field(default="", metadata={"json_optional": True})


@dataclass(frozen=True)
class AcceptedStructureRevision:
    task_id: str
    run_id: str
    revision: int
    actor: str
    input_sha256: str
    index_sha256: str
    accepted_path: str


@dataclass(frozen=True)
class AcceptedVerifierRevision:
    task_id: str
    run_id: str
    task_kind: str
    situation_id: str
    revision: int
    actor: str
    input_sha256: str
    audit_sha256: str

    def __post_init__(self) -> None:
        if self.task_kind not in {"SITUATION_AUDIT", "PROXY_AUDIT"}:
            raise MvpError("VERIFIER_REVISION_INVALID")


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise MvpError(f"cannot hash editor artifact: {path}") from exc


def _input_sha256(paths: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        resolved = path.resolve()
        digest.update(str(resolved).encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(resolved.read_bytes())
        except OSError as exc:
            raise MvpError(f"cannot hash editor input: {resolved}") from exc
        digest.update(b"\0")
    return digest.hexdigest()


def create_editor_task(
    run_dir: Path,
    run_id: str,
    situation_id: str,
    revision: int,
    input_paths: tuple[Path, ...],
    *,
    task_kind: str = "SITUATION",
    task_id: str | None = None,
    allowed_outputs: tuple[str, ...] = (
        "situation_draft.json",
        "narration_draft.json",
    ),
    expected_stage: str = "ANTIGRAVITY_EDITORIAL",
) -> EditorTask:
    from .antigravity import calculate_policy_sha256

    if revision < 1 or not input_paths or not allowed_outputs:
        raise MvpError("EDITOR_TASK_INVALID")
    resolved_inputs = tuple(path.resolve() for path in input_paths)
    task = EditorTask(
        task_id=task_id or f"{situation_id}-revision-{revision:03d}",
        run_id=run_id,
        situation_id=situation_id,
        revision=revision,
        expected_stage=expected_stage,
        input_paths=tuple(str(path) for path in resolved_inputs),
        input_sha256=_input_sha256(resolved_inputs),
        allowed_outputs=allowed_outputs,
        task_kind=task_kind,
        policy_sha256=calculate_policy_sha256(Path(__file__).resolve().parents[2]),
    )
    atomic_dump_json(run_dir / "editor_tasks" / f"{task.task_id}.json", task)
    return task


def load_editor_task(path: Path) -> EditorTask:
    return load_json(path, EditorTask)


def validate_task_inputs(task: EditorTask) -> None:
    from .antigravity import calculate_policy_sha256

    current_policy = calculate_policy_sha256(Path(__file__).resolve().parents[2])
    if not task.policy_sha256 or task.policy_sha256 != current_policy:
        raise MvpError("EDITOR_POLICY_HASH_CHANGED")
    current_input_hash = _input_sha256(tuple(Path(path) for path in task.input_paths))
    if current_input_hash != task.input_sha256:
        raise MvpError("EDITOR_INPUT_HASH_CHANGED")


def validate_task_submission(
    run_dir: Path,
    task: EditorTask,
    staging_dir: Path,
    *,
    staging_root: str,
) -> None:
    expected_dir = (run_dir / staging_root / task.task_id).resolve()
    if staging_dir.resolve() != expected_dir:
        raise MvpError("EDITOR_SUBMISSION_INVALID")
    try:
        actual_names = {path.name for path in expected_dir.iterdir() if path.is_file()}
    except OSError as exc:
        raise MvpError("EDITOR_SUBMISSION_INVALID") from exc
    if actual_names != set(task.allowed_outputs):
        raise MvpError("EDITOR_SUBMISSION_INVALID")


def _load_jsonl_ledger[T](path: Path, cls: type[T], error_code: str) -> tuple[T, ...]:
    if not path.exists():
        return ()
    records: list[T] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            raw = json.loads(line)
            records.append(cls(**raw))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        raise MvpError(f"cannot load {error_code}: {path}") from exc
    return tuple(records)


def load_editor_ledger(path: Path) -> tuple[AcceptedEditorialRevision, ...]:
    return _load_jsonl_ledger(path, AcceptedEditorialRevision, "editor ledger")


def load_verifier_ledger(path: Path) -> tuple[AcceptedVerifierRevision, ...]:
    return _load_jsonl_ledger(path, AcceptedVerifierRevision, "verifier ledger")


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, destination)
    except OSError as exc:
        raise MvpError(f"cannot accept editor artifact: {source}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def accept_antigravity_submission(
    run_dir: Path, task_id: str, staging_dir: Path
) -> AcceptedEditorialRevision:
    task_path = run_dir / "editor_tasks" / f"{task_id}.json"
    task = load_editor_task(task_path)
    if task.task_kind != "SITUATION":
        raise MvpError("EDITOR_TASK_KIND_INVALID")
    ledger_path = run_dir / "editor_ledger.jsonl"
    if any(
        record.situation_id == task.situation_id and record.revision >= task.revision
        for record in load_editor_ledger(ledger_path)
    ):
        raise MvpError("EDITOR_REVISION_STALE")
    validate_task_inputs(task)
    validate_task_submission(
        run_dir,
        task,
        staging_dir,
        staging_root="editor_staging",
    )
    sources = {name: staging_dir / name for name in task.allowed_outputs}
    try:
        for source in sources.values():
            json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MvpError("EDITOR_SUBMISSION_INVALID") from exc

    accepted_dir = (
        run_dir
        / "accepted_editorial"
        / task.situation_id
        / f"revision-{task.revision:03d}"
    )
    for name, source in sources.items():
        _atomic_copy(source, accepted_dir / name)
    accepted = AcceptedEditorialRevision(
        task_id=task.task_id,
        run_id=task.run_id,
        situation_id=task.situation_id,
        revision=task.revision,
        actor="ANTIGRAVITY",
        input_sha256=task.input_sha256,
        situation_sha256=_file_sha256(accepted_dir / "situation_draft.json"),
        narration_sha256=_file_sha256(accepted_dir / "narration_draft.json"),
        policy_sha256=task.policy_sha256,
    )
    atomic_append_jsonl(ledger_path, accepted)
    return accepted


def accept_antigravity_structure_submission(
    run_dir: Path, task_id: str, staging_dir: Path
) -> AcceptedStructureRevision:
    task = load_editor_task(run_dir / "editor_tasks" / f"{task_id}.json")
    if task.task_kind != "STRUCTURE" or task.allowed_outputs != (
        "situation_index_draft.json",
    ):
        raise MvpError("EDITOR_TASK_KIND_INVALID")
    validate_task_inputs(task)
    try:
        actual_names = {path.name for path in staging_dir.iterdir() if path.is_file()}
    except OSError as exc:
        raise MvpError("EDITOR_SUBMISSION_INVALID") from exc
    if actual_names != {"situation_index_draft.json"}:
        raise MvpError("EDITOR_SUBMISSION_INVALID")
    source = staging_dir / "situation_index_draft.json"
    try:
        json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MvpError("EDITOR_SUBMISSION_INVALID") from exc
    accepted_path = (
        run_dir
        / "accepted_structure"
        / f"revision-{task.revision:03d}"
        / "situation_index.json"
    )
    _atomic_copy(source, accepted_path)
    return AcceptedStructureRevision(
        task.task_id,
        task.run_id,
        task.revision,
        "ANTIGRAVITY",
        task.input_sha256,
        _file_sha256(accepted_path),
        str(accepted_path.resolve()),
    )


def require_antigravity_provenance(
    run_dir: Path, situation_id: str, artifact_paths: tuple[Path, Path]
) -> AcceptedEditorialRevision:
    situation_path = next(
        (path for path in artifact_paths if path.name == "situation_draft.json"), None
    )
    narration_path = next(
        (path for path in artifact_paths if path.name == "narration_draft.json"), None
    )
    if situation_path is None or narration_path is None:
        raise MvpError("EDITOR_PROVENANCE_INVALID")
    situation_hash = _file_sha256(situation_path)
    narration_hash = _file_sha256(narration_path)
    matching = [
        record
        for record in load_editor_ledger(run_dir / "editor_ledger.jsonl")
        if record.situation_id == situation_id
        and record.actor == "ANTIGRAVITY"
        and record.situation_sha256 == situation_hash
        and record.narration_sha256 == narration_hash
    ]
    if not matching:
        raise MvpError("EDITOR_PROVENANCE_INVALID")
    return max(matching, key=lambda record: record.revision)
