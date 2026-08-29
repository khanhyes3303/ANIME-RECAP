from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import MvpError
from .jsonio import dump_json, load_json
from .workspace import assert_inside_run

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PHASES = {"SCRIPT", "PROXY", "FINAL"}


def _non_empty(value: str, field: str) -> None:
    if not value.strip():
        raise MvpError(f"{field} must not be empty")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise MvpError(f"cannot hash file: {path}") from exc


def account_sha256(email: str) -> str:
    normalized = email.strip().casefold()
    if "@" not in normalized or not normalized.split("@", 1)[1]:
        raise MvpError("Google account email is invalid")
    return _sha256_text(normalized)


@dataclass(frozen=True, slots=True)
class GeminiUltraProfileBinding:
    account_sha256: str
    account_hint: str

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.account_sha256):
            raise MvpError("Gemini account fingerprint is invalid")
        _non_empty(self.account_hint, "Gemini account hint")
        if "@" not in self.account_hint or "***" not in self.account_hint:
            raise MvpError("Gemini account hint must be masked")


@dataclass(frozen=True, slots=True)
class GeminiUltraSessionReceipt:
    account_sha256: str
    account_hint: str
    plan_label: str
    model_label: str
    strongest_mode_confirmed: bool
    browser_status: str

    def __post_init__(self) -> None:
        if not _SHA256.fullmatch(self.account_sha256):
            raise MvpError("Gemini account fingerprint is invalid")
        if "@" not in self.account_hint or "***" not in self.account_hint:
            raise MvpError("Gemini account hint must be masked")
        if "ultra" not in self.plan_label.casefold():
            raise MvpError("Gemini Web session is not Google AI Ultra")
        if self.browser_status != "READY":
            raise MvpError("Gemini Web browser session is not ready")
        if not self.strongest_mode_confirmed or not self.model_label.strip():
            raise MvpError("Gemini Web strongest mode is not confirmed")


@dataclass(frozen=True, slots=True)
class GeminiWebRequest:
    run_id: str
    phase: str
    request_id: str
    artifact_path: str
    artifact_sha256: str
    evidence_sha256: str
    beat_ids: tuple[str, ...]
    prompt_path: str
    prompt_sha256: str
    evidence_paths: tuple[str, ...]

    def __post_init__(self) -> None:
        _non_empty(self.run_id, "web request run_id")
        if self.phase not in _PHASES:
            raise MvpError("Gemini Web request phase is invalid")
        _non_empty(self.request_id, "web request request_id")
        _non_empty(self.artifact_path, "web request artifact_path")
        if not _SHA256.fullmatch(self.artifact_sha256) or not _SHA256.fullmatch(
            self.evidence_sha256
        ):
            raise MvpError("Gemini Web request hash is invalid")
        if not self.beat_ids or len(set(self.beat_ids)) != len(self.beat_ids):
            raise MvpError("Gemini Web request beat IDs are invalid")
        _non_empty(self.prompt_path, "web request prompt_path")
        if not _SHA256.fullmatch(self.prompt_sha256):
            raise MvpError("Gemini Web prompt hash is invalid")
        if not self.evidence_paths:
            raise MvpError("Gemini Web request requires evidence paths")


@dataclass(frozen=True, slots=True)
class GeminiWebReceipt:
    run_id: str
    phase: str
    request_id: str
    request_sha256: str
    response_path: str
    response_sha256: str
    screenshot_paths: tuple[str, ...]
    session: GeminiUltraSessionReceipt
    raw_response_path: str
    raw_response_sha256: str

    def __post_init__(self) -> None:
        _non_empty(self.run_id, "web receipt run_id")
        if self.phase not in _PHASES:
            raise MvpError("Gemini Web receipt phase is invalid")
        _non_empty(self.request_id, "web receipt request_id")
        if not _SHA256.fullmatch(self.request_sha256) or not _SHA256.fullmatch(
            self.response_sha256
        ):
            raise MvpError("Gemini Web receipt hash is invalid")
        if not _SHA256.fullmatch(self.raw_response_sha256):
            raise MvpError("Gemini Web raw response hash is invalid")
        _non_empty(self.response_path, "web receipt response_path")
        _non_empty(self.raw_response_path, "web receipt raw_response_path")
        if self.response_path == self.raw_response_path:
            raise MvpError("Gemini Web raw response must be separate from critic JSON")
        if not self.screenshot_paths:
            raise MvpError("Gemini Web receipt requires a session screenshot")


@dataclass(frozen=True, slots=True)
class ArtifactFingerprint:
    name: str
    sha256: str
    dependency_sha256: str
    run_id: str

    def __post_init__(self) -> None:
        _non_empty(self.name, "artifact fingerprint name")
        _non_empty(self.run_id, "artifact fingerprint run_id")
        if not _SHA256.fullmatch(self.sha256) or not _SHA256.fullmatch(self.dependency_sha256):
            raise MvpError("artifact fingerprint hash is invalid")


@dataclass(frozen=True, slots=True)
class RunManifest:
    fingerprints: tuple[ArtifactFingerprint, ...]

    def __post_init__(self) -> None:
        if not self.fingerprints:
            raise MvpError("run manifest requires fingerprints")


def verify_receipt(
    run_dir: Path,
    receipt: GeminiWebReceipt,
    request_path: Path,
    binding: GeminiUltraProfileBinding,
) -> GeminiWebReceipt:
    if receipt.run_id != run_dir.resolve().name:
        raise MvpError("Gemini Web receipt belongs to another run")
    if receipt.session.account_sha256 != binding.account_sha256:
        raise MvpError("Gemini Web receipt account does not match the bound account")
    if receipt.session.account_hint != binding.account_hint:
        raise MvpError("Gemini Web receipt account hint does not match the bound account")
    request = _safe_run_file(request_path, run_dir, "request")
    if sha256_file(request) != receipt.request_sha256:
        raise MvpError("Gemini Web request hash does not match receipt")
    try:
        request_payload = json.loads(request.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MvpError("Gemini Web request is not valid JSON") from exc
    if request_payload.get("request_id") != receipt.request_id:
        raise MvpError("Gemini Web receipt request ID does not match request")
    if request_payload.get("phase") != receipt.phase:
        raise MvpError("Gemini Web receipt phase does not match request")
    response = _safe_run_file(Path(receipt.response_path), run_dir, "response")
    if sha256_file(response) != receipt.response_sha256:
        raise MvpError("Gemini Web response hash does not match receipt")
    raw_response = _safe_run_file(Path(receipt.raw_response_path), run_dir, "raw response")
    if sha256_file(raw_response) != receipt.raw_response_sha256:
        raise MvpError("Gemini Web raw response hash does not match receipt")
    for screenshot_path in receipt.screenshot_paths:
        _safe_run_file(Path(screenshot_path), run_dir, "session screenshot")
    return receipt


def _safe_run_file(path: Path, run_dir: Path, label: str) -> Path:
    if path.is_symlink():
        raise MvpError(f"{label} may not be a symlink")
    try:
        safe = assert_inside_run(path, run_dir)
    except (MvpError, OSError) as exc:
        raise MvpError(f"{label} path is outside run") from exc
    if not safe.is_file():
        raise MvpError(f"{label} does not exist: {path}")
    return safe


def write_profile_binding(path: Path, binding: GeminiUltraProfileBinding) -> None:
    dump_json(path, binding)


def load_profile_binding(path: Path) -> GeminiUltraProfileBinding:
    return load_json(path, GeminiUltraProfileBinding)


def canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_text(encoded)


def write_web_request(
    output_dir: Path,
    run_id: str,
    phase: str,
    artifact_path: Path,
    evidence_paths: tuple[Path, ...],
    beat_ids: tuple[str, ...],
    prompt_text: str,
) -> tuple[GeminiWebRequest, Path]:
    if not artifact_path.is_file():
        raise MvpError(f"Gemini Web artifact does not exist: {artifact_path}")
    if not evidence_paths or any(not path.is_file() for path in evidence_paths):
        raise MvpError("Gemini Web request evidence files are missing")
    _non_empty(prompt_text, "Gemini Web prompt")
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = output_dir / "prompt.txt"
    prompt_path.write_text(prompt_text, encoding="utf-8")
    resolved_evidence = tuple(
        str(path.resolve()) for path in sorted(evidence_paths, key=lambda item: str(item))
    )
    evidence_payload = {
        "files": [
            {"path": path, "sha256": sha256_file(Path(path))}
            for path in resolved_evidence
        ]
    }
    payload = {
        "run_id": run_id,
        "phase": phase,
        "artifact_path": str(artifact_path.resolve()),
        "artifact_sha256": sha256_file(artifact_path),
        "evidence_sha256": canonical_sha256(evidence_payload),
        "beat_ids": list(beat_ids),
        "prompt_path": str(prompt_path.resolve()),
        "prompt_sha256": sha256_file(prompt_path),
        "evidence_paths": list(resolved_evidence),
    }
    request = GeminiWebRequest(
        run_id,
        phase,
        canonical_sha256(payload),
        str(artifact_path.resolve()),
        payload["artifact_sha256"],
        payload["evidence_sha256"],
        beat_ids,
        payload["prompt_path"],
        payload["prompt_sha256"],
        resolved_evidence,
    )
    request_path = output_dir / "request.json"
    dump_json(request_path, request)
    run_root = output_dir.parent.parent
    write_run_manifest(
        run_root,
        (
            ArtifactFingerprint(
                f"{phase.casefold()}_request",
                sha256_file(request_path),
                canonical_sha256(
                    {
                        "artifact_sha256": request.artifact_sha256,
                        "evidence_sha256": request.evidence_sha256,
                    }
                ),
                run_id,
            ),
        ),
    )
    return request, request_path


def reset_web_phase(run_dir: Path, phase: str) -> Path:
    phase_upper = phase.upper()
    if phase_upper not in _PHASES:
        raise MvpError("Gemini Web phase is invalid")
    phase_dir = run_dir / "gemini_web" / phase.casefold()
    phase_dir.mkdir(parents=True, exist_ok=True)
    generated_names = {
        "evidence",
        "request.json",
        "prompt.txt",
        "response.txt",
        "receipt.json",
        "screenshots",
        f"critic_{phase.casefold()}.json",
    }
    for child in phase_dir.iterdir():
        if child.name not in generated_names:
            continue
        if child.is_symlink():
            raise MvpError(f"Gemini Web phase artifact may not be a symlink: {child}")
        assert_inside_run(child, run_dir)
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    return phase_dir


def load_verified_web_review[T](run_dir: Path, phase: str, review_cls: type[T]) -> T:
    phase_upper = phase.upper()
    if phase_upper not in _PHASES:
        raise MvpError("Gemini Web review phase is invalid")
    phase_dir = run_dir / "gemini_web" / phase.casefold()
    request_path = phase_dir / "request.json"
    receipt_path = phase_dir / "receipt.json"
    review_path = phase_dir / f"critic_{phase.casefold()}.json"
    binding_path = run_dir.parent.parent / ".local" / "gemini_ultra_profile.json"
    request = load_json(request_path, GeminiWebRequest)
    receipt = load_json(receipt_path, GeminiWebReceipt)
    binding = load_profile_binding(binding_path)
    verify_receipt(run_dir, receipt, request_path, binding)
    verify_request_dependencies(run_dir, request)
    if Path(receipt.response_path).resolve() != review_path.resolve():
        raise MvpError("Gemini Web response must be the engine-declared critic JSON")
    return load_json(review_path, review_cls)


def load_operator_verified_review[T](
    run_dir: Path,
    phase: str,
    review_cls: type[T],
    *,
    ledger: object,
) -> T:
    """Load a critic result only when it is bound to a signed operator transaction."""
    from .gemini_operator import (
        OperatorLedger,
        OperatorPolicy,
        OperatorReceipt,
        OperatorRequest,
        validate_browser_evidence,
        verify_operator_receipt,
    )

    if not isinstance(ledger, OperatorLedger):
        raise MvpError("operator ledger is invalid")
    phase_upper = phase.upper()
    if phase_upper not in _PHASES:
        raise MvpError("operator review phase is invalid")
    phase_dir = run_dir / "gemini_web" / phase_upper.casefold()
    request = load_json(phase_dir / "operator_request.json", OperatorRequest)
    receipt = load_json(phase_dir / "operator_receipt.json", OperatorReceipt)
    verify_operator_receipt(receipt, ledger, expected_request=request)
    if request.run_id != run_dir.resolve().name or request.phase != phase_upper:
        raise MvpError("operator request belongs to another run or phase")

    critic = _safe_run_file(Path(receipt.critic_path), run_dir, "operator critic")
    raw = _safe_run_file(Path(receipt.raw_response_path), run_dir, "operator raw response")
    screenshot = _safe_run_file(
        Path(receipt.observation.screenshot_path), run_dir, "operator screenshot"
    )
    expected_critic = phase_dir / f"critic_{phase_upper.casefold()}.json"
    if critic.resolve() != expected_critic.resolve():
        raise MvpError("operator critic path is not engine-declared")
    hashes = (
        (critic, receipt.critic_sha256, "critic"),
        (raw, receipt.raw_response_sha256, "raw response"),
        (screenshot, receipt.screenshot_sha256, "screenshot"),
    )
    for path, expected_hash, label in hashes:
        if sha256_file(path) != expected_hash:
            raise MvpError(f"operator {label} hash does not match receipt")

    manifest = _safe_run_file(
        phase_dir / "operator_packet" / "manifest.json",
        run_dir,
        "operator packet",
    )
    if sha256_file(manifest) != request.packet_sha256:
        raise MvpError("operator packet hash does not match request")
    try:
        packet_payload = json.loads(manifest.read_text(encoding="utf-8"))
        files = packet_payload["files"]
        if packet_payload["phase"] != phase_upper or not files:
            raise MvpError("operator packet identity is invalid")
        for item in files:
            path = _safe_run_file(Path(item["path"]), run_dir, "operator packet file")
            if sha256_file(path) != item["sha256"]:
                raise MvpError("operator packet file hash does not match")
        if files[0]["sha256"] != request.artifact_sha256:
            raise MvpError("operator artifact hash does not match request")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MvpError("operator packet is malformed") from exc

    validate_browser_evidence(
        receipt.observation,
        OperatorPolicy.required(),
        raw_response=raw,
        critic=critic,
    )
    return load_json(critic, review_cls)


def verify_request_dependencies(run_dir: Path, request: GeminiWebRequest) -> None:
    artifact = _safe_project_file(Path(request.artifact_path), run_dir, "artifact")
    if sha256_file(artifact) != request.artifact_sha256:
        raise MvpError("Gemini Web artifact hash does not match request")
    evidence: list[dict[str, str]] = []
    for raw_path in request.evidence_paths:
        path = _safe_run_file(Path(raw_path), run_dir, "evidence")
        evidence.append({"path": str(path.resolve()), "sha256": sha256_file(path)})
    if canonical_sha256({"files": evidence}) != request.evidence_sha256:
        raise MvpError("Gemini Web evidence hash does not match request")
    prompt = _safe_run_file(Path(request.prompt_path), run_dir, "prompt")
    if sha256_file(prompt) != request.prompt_sha256:
        raise MvpError("Gemini Web prompt hash does not match request")


def _safe_project_file(path: Path, run_dir: Path, label: str) -> Path:
    if path.is_symlink():
        raise MvpError(f"{label} may not be a symlink")
    root = run_dir.parent.parent.resolve()
    resolved = path.resolve(strict=False)
    if resolved != root and root not in resolved.parents:
        raise MvpError(f"{label} path is outside project")
    if not resolved.is_file():
        raise MvpError(f"{label} does not exist: {path}")
    return resolved


def write_run_manifest(run_dir: Path, fingerprints: tuple[ArtifactFingerprint, ...]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "run_manifest.json"
    existing: tuple[ArtifactFingerprint, ...] = ()
    if path.is_file():
        existing = load_json(path, RunManifest).fingerprints
    by_name = {item.name: item for item in existing}
    by_name.update({item.name: item for item in fingerprints})
    manifest = RunManifest(tuple(by_name[name] for name in sorted(by_name)))
    dump_json(path, manifest)
    return path
