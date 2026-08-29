from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.gemini_web import (
    ArtifactFingerprint,
    GeminiUltraProfileBinding,
    GeminiUltraSessionReceipt,
    GeminiWebReceipt,
    canonical_sha256,
    load_verified_web_review,
    reset_web_phase,
    sha256_file,
    verify_receipt,
    write_run_manifest,
    write_web_request,
)
from anime_review_mvp.jsonio import dump_json
from anime_review_mvp.models import CriticBeatReview, CriticReviewDocument


def _write_web_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    request = tmp_path / "request.json"
    response = tmp_path / "critic.json"
    raw_response = tmp_path / "response.txt"
    screenshot = tmp_path / "session.png"
    request.write_text('{"request_id":"req-01","phase":"FINAL"}\n', encoding="utf-8")
    response.write_text('{"phase":"FINAL","beat_reviews":[]}\n', encoding="utf-8")
    raw_response.write_text("raw Gemini response\n", encoding="utf-8")
    screenshot.write_bytes(b"png")
    return request, response, raw_response, screenshot


def test_receipt_requires_ultra_and_exact_request_response_hashes(tmp_path: Path) -> None:
    request_path, response_path, raw_response_path, screenshot = _write_web_fixture(tmp_path)
    binding = GeminiUltraProfileBinding(
        hashlib.sha256(b"ultra@example.com").hexdigest(), "ul***@example.com"
    )
    receipt = GeminiWebReceipt(
        tmp_path.name,
        "FINAL",
        "req-01",
        sha256_file(request_path),
        str(response_path),
        sha256_file(response_path),
        (str(screenshot),),
        GeminiUltraSessionReceipt(
            binding.account_sha256,
            binding.account_hint,
            "Google AI Ultra",
            "Deep Think",
            True,
            "READY",
        ),
        str(raw_response_path),
        sha256_file(raw_response_path),
    )

    verified = verify_receipt(tmp_path, receipt, request_path, binding)

    assert verified.phase == "FINAL"


def test_session_rejects_non_ultra_or_non_ready_browser() -> None:
    with pytest.raises(MvpError, match="Google AI Ultra"):
        GeminiUltraSessionReceipt(
            "a" * 64, "a***@example.com", "Google AI Pro", "Deep Think", True, "READY"
        )
    with pytest.raises(MvpError, match="not ready"):
        GeminiUltraSessionReceipt(
            "a" * 64, "a***@example.com", "Google AI Ultra", "Deep Think", True, "CAPTCHA"
        )


def test_receipt_rejects_account_hash_or_response_hash_mismatch(tmp_path: Path) -> None:
    request_path, response_path, raw_response_path, screenshot = _write_web_fixture(tmp_path)
    binding = GeminiUltraProfileBinding("b" * 64, "b***@example.com")
    receipt = GeminiWebReceipt(
        tmp_path.name,
        "FINAL",
        "req-01",
        sha256_file(request_path),
        str(response_path),
        "0" * 64,
        (str(screenshot),),
        GeminiUltraSessionReceipt(
            binding.account_sha256,
            binding.account_hint,
            "Google AI Ultra",
            "Deep Think",
            True,
            "READY",
        ),
        str(raw_response_path),
        sha256_file(raw_response_path),
    )

    with pytest.raises(MvpError, match="response hash"):
        verify_receipt(tmp_path, receipt, request_path, binding)

    wrong_binding = GeminiUltraProfileBinding("c" * 64, "c***@example.com")
    receipt = GeminiWebReceipt(
        tmp_path.name,
        "FINAL",
        "req-01",
        sha256_file(request_path),
        str(response_path),
        sha256_file(response_path),
        (str(screenshot),),
        GeminiUltraSessionReceipt(
            binding.account_sha256,
            binding.account_hint,
            "Google AI Ultra",
            "Deep Think",
            True,
            "READY",
        ),
        str(raw_response_path),
        sha256_file(raw_response_path),
    )
    with pytest.raises(MvpError, match="account"):
        verify_receipt(tmp_path, receipt, request_path, wrong_binding)


def test_receipt_rejects_missing_screenshot_and_path_outside_run(tmp_path: Path) -> None:
    request_path, response_path, raw_response_path, _ = _write_web_fixture(tmp_path)
    binding = GeminiUltraProfileBinding("a" * 64, "a***@example.com")
    with pytest.raises(MvpError, match="screenshot"):
        GeminiWebReceipt(
            tmp_path.name,
            "FINAL",
            "req-01",
            sha256_file(request_path),
            str(response_path),
            sha256_file(response_path),
            (),
            GeminiUltraSessionReceipt(
                binding.account_sha256,
                binding.account_hint,
                "Google AI Ultra",
                "Deep Think",
                True,
                "READY",
            ),
            str(raw_response_path),
            sha256_file(raw_response_path),
        )

    outside = tmp_path.parent / "outside.txt"
    outside.write_text("response", encoding="utf-8")
    receipt = GeminiWebReceipt(
        tmp_path.name,
        "FINAL",
        "req-01",
        sha256_file(request_path),
        str(outside),
        sha256_file(outside),
        (str(tmp_path / "session.png"),),
        GeminiUltraSessionReceipt(
            binding.account_sha256,
            binding.account_hint,
            "Google AI Ultra",
            "Deep Think",
            True,
            "READY",
        ),
        str(raw_response_path),
        sha256_file(raw_response_path),
    )
    with pytest.raises(MvpError, match="run"):
        verify_receipt(tmp_path, receipt, request_path, binding)


def test_write_web_request_hashes_artifact_and_evidence(tmp_path: Path) -> None:
    artifact = tmp_path / "storyboard.json"
    evidence = tmp_path / "frame.jpg"
    artifact.write_text('{"beat":"beat-001"}\n', encoding="utf-8")
    evidence.write_bytes(b"frame")

    request, request_path = write_web_request(
        tmp_path / "gemini_web" / "script",
        "run-01",
        "SCRIPT",
        artifact,
        (evidence,),
        ("beat-001",),
        "Return JSON only.",
    )

    assert request.phase == "SCRIPT"
    assert request.request_id
    assert request_path.is_file()
    assert request.artifact_sha256 == sha256_file(artifact)
    assert request.evidence_sha256 == canonical_sha256(
        {"files": [{"path": str(evidence.resolve()), "sha256": sha256_file(evidence)}]}
    )
    assert (tmp_path / "run_manifest.json").is_file()


def test_reset_web_phase_removes_only_current_phase_generated_files(tmp_path: Path) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-01"
    phase_dir = run / "gemini_web" / "final"
    evidence = phase_dir / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "old.jpg").write_bytes(b"old")
    (phase_dir / "request.json").write_text("old", encoding="utf-8")
    (phase_dir / "keep.txt").write_text("keep", encoding="utf-8")

    reset_web_phase(run, "FINAL")

    assert not evidence.exists()
    assert not (phase_dir / "request.json").exists()
    assert (phase_dir / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_load_verified_web_review_requires_response_to_be_the_review_json(tmp_path: Path) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-01"
    phase_dir = run / "gemini_web" / "final"
    artifact = run / "artifact.json"
    evidence = run / "evidence.jpg"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("artifact", encoding="utf-8")
    evidence.write_bytes(b"evidence")
    request, request_path = write_web_request(
        phase_dir, run.name, "FINAL", artifact, (evidence,), ("beat-001",), "JSON only"
    )
    response = phase_dir / "critic_final.json"
    review = CriticReviewDocument(
        "VIDEO",
        "producer-01",
        "gemini-ultra-final",
        (
            CriticBeatReview(
                "beat-001",
                (),
                ("anchor-001",),
                "Jiro đứng.",
                "Jiro đứng.",
                "MATCH",
                "Khớp.",
            ),
        ),
    )
    dump_json(response, review)
    raw_response = phase_dir / "response.txt"
    raw_response.write_text("raw Gemini response", encoding="utf-8")
    screenshot = phase_dir / "screenshots" / "session.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"screen")
    binding = GeminiUltraProfileBinding("a" * 64, "a***@example.com")
    (tmp_path / ".local").mkdir()
    dump_json(tmp_path / ".local" / "gemini_ultra_profile.json", binding)
    dump_json(
        phase_dir / "receipt.json",
        GeminiWebReceipt(
            run.name,
            "FINAL",
            request.request_id,
            sha256_file(request_path),
            str(response),
            sha256_file(response),
            (str(screenshot),),
            GeminiUltraSessionReceipt(
                binding.account_sha256,
                binding.account_hint,
                "Google AI Ultra",
                "Deep Think",
                True,
                "READY",
            ),
            str(raw_response),
            sha256_file(raw_response),
        ),
    )

    loaded = load_verified_web_review(run, "final", CriticReviewDocument)

    assert loaded == review


def test_load_verified_web_review_rejects_stale_artifact_dependency(tmp_path: Path) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-01"
    phase_dir = run / "gemini_web" / "final"
    artifact = run / "final_candidate.mp4"
    evidence = run / "evidence.jpg"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"candidate-v1")
    evidence.write_bytes(b"evidence")
    request, request_path = write_web_request(
        phase_dir, run.name, "FINAL", artifact, (evidence,), ("beat-001",), "JSON only"
    )
    response = phase_dir / "critic_final.json"
    review = CriticReviewDocument(
        "VIDEO", "producer-01", "gemini-ultra-final",
        (CriticBeatReview("beat-001", (), ("anchor-001",), "Hình.", "Lời.", "MATCH", "Khớp."),),
    )
    dump_json(response, review)
    raw_response = phase_dir / "response.txt"
    raw_response.write_text("raw Gemini response", encoding="utf-8")
    screenshot = phase_dir / "screenshots" / "session.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.write_bytes(b"screen")
    binding = GeminiUltraProfileBinding("a" * 64, "a***@example.com")
    (tmp_path / ".local").mkdir()
    dump_json(tmp_path / ".local" / "gemini_ultra_profile.json", binding)
    dump_json(
        phase_dir / "receipt.json",
        GeminiWebReceipt(
            run.name, "FINAL", request.request_id, sha256_file(request_path),
            str(response), sha256_file(response), (str(screenshot),),
            GeminiUltraSessionReceipt(
                binding.account_sha256,
                binding.account_hint,
                "Google AI Ultra",
                "Deep Think",
                True,
                "READY",
            ),
            str(raw_response),
            sha256_file(raw_response),
        ),
    )
    artifact.write_bytes(b"candidate-v2")

    with pytest.raises(MvpError, match="artifact hash"):
        load_verified_web_review(run, "final", CriticReviewDocument)


def test_run_manifest_records_fingerprint_and_rejects_stale_run_id(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"v1")
    entry = ArtifactFingerprint(
        "final_candidate",
        sha256_file(artifact),
        canonical_sha256({"source": "source-v1"}),
        "run-01",
    )

    manifest_path = write_run_manifest(tmp_path, (entry,))

    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["fingerprints"][0]["run_id"] == "run-01"
