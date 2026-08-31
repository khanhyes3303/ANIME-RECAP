from __future__ import annotations

import json
from pathlib import Path

import pytest

from anime_review_mvp.editor_provenance import AcceptedVerifierRevision
from anime_review_mvp.errors import MvpError
from anime_review_mvp.jsonio import atomic_append_jsonl
from anime_review_mvp.proxy_approval import (
    approve_proxy,
    content_sha256,
    reject_proxy,
    require_approved_artifacts,
    sha256_file,
)
from anime_review_mvp.workflow import Stage, new_state, read_state


def _prepared(tmp_path: Path) -> tuple[Path, Path, tuple[Path, ...]]:
    run = tmp_path / "run"
    new_state(run, stage=Stage.CHO_NGUOI_DUNG_DUYET_PROXY)
    proxy = run / "proxy.mp4"
    plan = run / "narration_plan.json"
    timeline = run / "semantic_timeline.json"
    proxy.write_bytes(b"proxy-video")
    plan.write_text('{"plan":1}', encoding="utf-8")
    timeline.write_text('{"timeline":1}', encoding="utf-8")
    return run, proxy, (plan, timeline)


def test_approve_proxy_records_proxy_and_editorial_hashes(tmp_path: Path) -> None:
    run, proxy, artifacts = _prepared(tmp_path)
    approval = approve_proxy(run, proxy, artifacts, now_utc=lambda: "2026-08-30T00:00:00Z")
    assert approval.proxy_sha256 == sha256_file(proxy)
    assert approval.editorial_sha256 == content_sha256(artifacts)
    assert read_state(run).stage is Stage.DUNG_VIDEO_CUOI


def test_final_guard_rejects_changed_narration_after_approval(tmp_path: Path) -> None:
    run, proxy, artifacts = _prepared(tmp_path)
    approve_proxy(run, proxy, artifacts)
    artifacts[0].write_text("changed", encoding="utf-8")
    with pytest.raises(MvpError, match="APPROVED_ARTIFACT_HASH_CHANGED"):
        require_approved_artifacts(run, artifacts)


def test_rejection_preserves_proxy_and_routes_note_to_antigravity(tmp_path: Path) -> None:
    run, proxy, _artifacts = _prepared(tmp_path)
    rejected = reject_proxy(
        run, "Voice nói ông nội trước hình.", ("situation-004",),
        now_utc=lambda: "2026-08-30T00:00:00Z",
    )
    assert proxy.exists()
    assert rejected.stage is Stage.CHO_ANTIGRAVITY_TINH_HUONG
    assert rejected.current_situation_id == "situation-004"


def test_v2_approval_requires_current_proxy_verifier_artifact(tmp_path: Path) -> None:
    run, proxy, artifacts = _prepared(tmp_path)
    raw_state = json.loads((run / "run_state.json").read_text(encoding="utf-8"))
    raw_state["editorial_revision"] = 1
    (run / "run_state.json").write_text(json.dumps(raw_state), encoding="utf-8")
    (run / "proxy_evidence").mkdir()
    (run / "proxy_evidence" / "proxy_evidence_manifest.json").write_text(
        "{}", encoding="utf-8"
    )
    accepted_audit = run / "accepted_verification" / "proxy" / "proxy_audit.json"
    accepted_audit.parent.mkdir(parents=True)
    accepted_audit.write_text('{"verdict":"MATCH"}', encoding="utf-8")
    atomic_append_jsonl(
        run / "verifier_ledger.jsonl",
        AcceptedVerifierRevision(
            "proxy-audit-001",
            run.name,
            "PROXY_AUDIT",
            "__episode__",
            1,
            "ANTIGRAVITY_VERIFIER",
            "a" * 64,
            sha256_file(accepted_audit),
        ),
    )

    approval = approve_proxy(run, proxy, artifacts)
    assert approval.proxy_sha256 == sha256_file(proxy)


def test_v2_approval_rejects_stale_proxy_verifier_revision(tmp_path: Path) -> None:
    run, proxy, artifacts = _prepared(tmp_path)
    raw_state = json.loads((run / "run_state.json").read_text(encoding="utf-8"))
    raw_state["editorial_revision"] = 2
    (run / "run_state.json").write_text(json.dumps(raw_state), encoding="utf-8")
    (run / "proxy_evidence").mkdir()
    (run / "proxy_evidence" / "proxy_evidence_manifest.json").write_text(
        "{}", encoding="utf-8"
    )
    accepted_audit = run / "accepted_verification" / "proxy" / "proxy_audit.json"
    accepted_audit.parent.mkdir(parents=True)
    accepted_audit.write_text('{"verdict":"MATCH"}', encoding="utf-8")
    atomic_append_jsonl(
        run / "verifier_ledger.jsonl",
        AcceptedVerifierRevision(
            "proxy-audit-001",
            run.name,
            "PROXY_AUDIT",
            "__episode__",
            1,
            "ANTIGRAVITY_VERIFIER",
            "a" * 64,
            sha256_file(accepted_audit),
        ),
    )

    with pytest.raises(MvpError, match="accepted Antigravity proxy verifier"):
        approve_proxy(run, proxy, artifacts)
