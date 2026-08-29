from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from .errors import MvpError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class OperatorPolicy:
    model_label: str
    mode_label: str
    plan_token: str
    minimum_session_seconds: float

    @classmethod
    def required(cls) -> OperatorPolicy:
        return cls("3.7 Flash", "Tư duy mở rộng", "Ultra", 3.0)


@dataclass(frozen=True, slots=True)
class BrowserObservation:
    account_sha256: str
    account_hint: str
    plan_label: str
    model_label: str
    mode_label: str
    conversation_url: str
    chrome_pid: int
    screenshot_path: str
    started_at: str
    finished_at: str


@dataclass(frozen=True, slots=True)
class OperatorRequest:
    run_id: str
    phase: str
    nonce: str
    request_sha256: str
    artifact_sha256: str
    packet_sha256: str
    issued_at: str


@dataclass(frozen=True, slots=True)
class OperatorReceipt:
    run_id: str
    phase: str
    nonce: str
    request_sha256: str
    artifact_sha256: str
    packet_sha256: str
    observation: BrowserObservation
    screenshot_sha256: str
    raw_response_path: str
    raw_response_sha256: str
    critic_path: str
    critic_sha256: str
    operator_build_sha256: str
    ledger_signature: str = ""


def _canonical_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _receipt_payload(receipt: OperatorReceipt) -> dict[str, object]:
    payload = asdict(receipt)
    payload.pop("ledger_signature")
    return payload


def _request_payload(request: OperatorRequest) -> dict[str, str]:
    payload = asdict(request)
    payload.pop("request_sha256")
    return payload


def issue_request(
    run_id: str,
    phase: str,
    artifact_sha256: str,
    packet_sha256: str,
    *,
    nonce: str | None = None,
    issued_at: str | None = None,
) -> OperatorRequest:
    request = OperatorRequest(
        run_id=run_id,
        phase=phase,
        nonce=nonce or secrets.token_urlsafe(32),
        request_sha256="",
        artifact_sha256=artifact_sha256,
        packet_sha256=packet_sha256,
        issued_at=issued_at or datetime.now(UTC).isoformat(),
    )
    digest = hashlib.sha256(_canonical_json(_request_payload(request))).hexdigest()
    return replace(request, request_sha256=digest)


class OperatorLedger:
    def __init__(self, path: Path, key: bytes) -> None:
        if len(key) < 32:
            raise MvpError("operator ledger key must contain at least 32 bytes")
        self.path = path
        self._key = key

    def append(self, receipt: OperatorReceipt) -> str:
        if receipt.ledger_signature:
            raise MvpError("ledger only accepts unsigned operator receipts")
        payload = _receipt_payload(receipt)
        canonical = _canonical_json(payload)
        signature = hmac.new(self._key, canonical, hashlib.sha256).hexdigest()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    {"payload": payload, "signature": signature},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            )
        return signature

    def verified_entry(self, nonce: str) -> OperatorReceipt:
        matches: list[tuple[OperatorReceipt, str]] = []
        if not self.path.is_file():
            raise MvpError("operator receipt has no unique ledger entry")
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                entry = json.loads(line)
                payload = entry["payload"]
                signature = entry["signature"]
                expected = hmac.new(
                    self._key,
                    _canonical_json(payload),
                    hashlib.sha256,
                ).hexdigest()
                if not hmac.compare_digest(signature, expected):
                    raise MvpError("operator ledger signature is invalid")
                if payload.get("nonce") == nonce:
                    raw = dict(payload)
                    raw["observation"] = BrowserObservation(**raw["observation"])
                    matches.append((OperatorReceipt(**raw), signature))
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise MvpError("operator ledger is malformed") from exc
        if len(matches) != 1:
            raise MvpError("operator receipt has no unique ledger entry")
        receipt, signature = matches[0]
        return replace(receipt, ledger_signature=signature)


def verify_operator_receipt(
    receipt: OperatorReceipt,
    ledger: OperatorLedger,
    *,
    expected_request: OperatorRequest,
) -> OperatorReceipt:
    recorded = ledger.verified_entry(receipt.nonce)
    if recorded != receipt:
        raise MvpError("operator receipt does not match signed ledger entry")
    request_fields = (
        "run_id",
        "phase",
        "nonce",
        "request_sha256",
        "artifact_sha256",
        "packet_sha256",
    )
    if any(getattr(receipt, name) != getattr(expected_request, name) for name in request_fields):
        raise MvpError("operator receipt does not match expected request")
    return receipt


def load_or_create_ledger_key(path: Path) -> bytes:
    if path.is_file():
        key = path.read_bytes()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(32)
        path.write_bytes(key)
    if len(key) != 32:
        raise MvpError("operator ledger key is invalid")
    return key


def validate_session_screenshot(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 20_000:
        raise MvpError("Gemini session screenshot is missing or too small")
    try:
        with Image.open(path) as source:
            if source.format not in {"PNG", "JPEG"}:
                raise MvpError("Gemini session screenshot must be PNG or JPEG")
            if source.width < 1_000 or source.height < 600:
                raise MvpError("Gemini session screenshot dimensions are too small")
            sample = source.convert("RGB").resize((160, 90))
            colors = sample.getcolors(maxcolors=160 * 90)
            if colors is None or len(colors) < 32:
                raise MvpError("Gemini session screenshot is effectively solid")
            histogram = sample.convert("L").histogram()
    except (OSError, ValueError) as exc:
        raise MvpError("Gemini session screenshot is unreadable") from exc
    total = sum(histogram)
    entropy = -sum(
        (count / total) * math.log2(count / total) for count in histogram if count
    )
    if entropy < 1.5:
        raise MvpError("Gemini session screenshot has insufficient visual entropy")


def validate_browser_evidence(
    observation: BrowserObservation,
    policy: OperatorPolicy,
    *,
    raw_response: Path,
    critic: Path,
) -> None:
    if observation.model_label != policy.model_label:
        raise MvpError(f"Gemini model must be {policy.model_label}")
    if observation.mode_label != policy.mode_label:
        raise MvpError(f"Gemini mode must be {policy.mode_label}")
    if policy.plan_token.casefold() not in observation.plan_label.casefold():
        raise MvpError("Gemini account is not Ultra")
    if not _SHA256.fullmatch(observation.account_sha256):
        raise MvpError("Gemini account fingerprint is invalid")
    if "***" not in observation.account_hint or "@" not in observation.account_hint:
        raise MvpError("Gemini account hint must be masked")
    parsed = urlparse(observation.conversation_url)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "gemini.google.com"
        or not parsed.path.startswith("/app/")
        or parsed.path.rstrip("/") == "/app"
    ):
        raise MvpError("Gemini conversation URL is not a real chat")
    if observation.chrome_pid <= 0:
        raise MvpError("Gemini Chrome PID is invalid")
    try:
        started = datetime.fromisoformat(observation.started_at)
        finished = datetime.fromisoformat(observation.finished_at)
    except ValueError as exc:
        raise MvpError("Gemini session timestamps are invalid") from exc
    if (finished - started).total_seconds() < policy.minimum_session_seconds:
        raise MvpError("Gemini browser session completed implausibly quickly")
    if not raw_response.is_file() or not critic.is_file():
        raise MvpError("Gemini raw response or critic is missing")
    if raw_response.resolve() == critic.resolve():
        raise MvpError("Gemini raw response must be separate from critic")
    if raw_response.read_bytes() == critic.read_bytes():
        raise MvpError("Gemini raw response must differ from normalized critic")
    validate_session_screenshot(Path(observation.screenshot_path))
