from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .editor_provenance import load_verifier_ledger
from .errors import MvpError
from .jsonio import atomic_dump_json, load_json
from .workflow import (
    RunState,
    Stage,
    approve_proxy_state,
    read_state,
    reject_proxy_state,
)

Clock = Callable[[], str]


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ProxyApproval:
    run_id: str
    revision: int
    proxy_path: str
    proxy_sha256: str
    editorial_sha256: str
    editorial_paths: tuple[str, ...]
    approved_at_utc: str


@dataclass(frozen=True, slots=True)
class ProxyRejection:
    run_id: str
    revision: int
    note: str
    situation_ids: tuple[str, ...]
    rejected_at_utc: str


def sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise MvpError(f"approval artifact does not exist: {path}") from exc


def content_sha256(paths: tuple[Path, ...]) -> str:
    if not paths:
        raise MvpError("proxy approval requires editorial artifacts")
    digest = hashlib.sha256()
    for path in sorted((item.resolve() for item in paths), key=lambda item: str(item).casefold()):
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError as exc:
            raise MvpError(f"approval artifact does not exist: {path}") from exc
        digest.update(b"\0")
    return digest.hexdigest()


def approve_proxy(
    run_dir: Path,
    proxy_path: Path,
    editorial_paths: tuple[Path, ...],
    *,
    now_utc: Clock = utc_now,
) -> ProxyApproval:
    state = read_state(run_dir)
    if state.stage is not Stage.CHO_NGUOI_DUNG_DUYET_PROXY:
        raise MvpError("proxy approval is only valid while waiting for the user")
    if state.editorial_revision >= 1 and (
        run_dir / "proxy_evidence" / "proxy_evidence_manifest.json"
    ).is_file():
        accepted_proxy_verifiers = tuple(
            record for record in load_verifier_ledger(run_dir / "verifier_ledger.jsonl")
            if record.task_kind == "PROXY_AUDIT"
            and record.actor == "ANTIGRAVITY_VERIFIER"
            and record.revision == state.editorial_revision
        )
        if not accepted_proxy_verifiers:
            raise MvpError("proxy approval requires accepted Antigravity proxy verifier audit")
        accepted_audit = run_dir / "accepted_verification" / "proxy" / "proxy_audit.json"
        current_audit_hash = (
            sha256_file(accepted_audit) if accepted_audit.is_file() else ""
        )
        if current_audit_hash != accepted_proxy_verifiers[-1].audit_sha256:
            raise MvpError("proxy approval verifier audit artifact is stale or missing")
    proxy_hash = sha256_file(proxy_path)
    editorial_hash = content_sha256(editorial_paths)
    approval = ProxyApproval(
        run_dir.name,
        max(1, state.editorial_revision),
        str(proxy_path.resolve()),
        proxy_hash,
        editorial_hash,
        tuple(str(path.resolve()) for path in editorial_paths),
        now_utc(),
    )
    atomic_dump_json(run_dir / "proxy_approval.json", approval)
    approve_proxy_state(run_dir, proxy_hash, editorial_hash)
    return approval


def require_approved_artifacts(
    run_dir: Path,
    editorial_paths: tuple[Path, ...] = (),
) -> ProxyApproval:
    state = read_state(run_dir)
    if not state.approved_proxy_sha256 or not state.approved_artifact_sha256:
        raise MvpError("proxy approval is required before final render")
    approval = load_json(run_dir / "proxy_approval.json", ProxyApproval)
    checked_paths = editorial_paths or tuple(Path(path) for path in approval.editorial_paths)
    if (
        content_sha256(checked_paths) != approval.editorial_sha256
        or state.approved_artifact_sha256 != approval.editorial_sha256
    ):
        raise MvpError("APPROVED_ARTIFACT_HASH_CHANGED")
    proxy = Path(approval.proxy_path)
    if (
        sha256_file(proxy) != approval.proxy_sha256
        or state.approved_proxy_sha256 != approval.proxy_sha256
    ):
        raise MvpError("APPROVED_PROXY_HASH_CHANGED")
    return approval


def reject_proxy(
    run_dir: Path,
    note: str,
    situation_ids: tuple[str, ...],
    *,
    now_utc: Clock = utc_now,
) -> RunState:
    state = read_state(run_dir)
    if state.stage is not Stage.CHO_NGUOI_DUNG_DUYET_PROXY:
        raise MvpError("proxy can only be rejected while waiting for user approval")
    revision = max(1, state.editorial_revision)
    rejection = ProxyRejection(
        run_dir.name,
        revision,
        note.strip(),
        situation_ids,
        now_utc(),
    )
    atomic_dump_json(
        run_dir / "proxy_rejections" / f"revision-{revision:03d}.json",
        rejection,
    )
    return reject_proxy_state(run_dir, note, situation_ids)
