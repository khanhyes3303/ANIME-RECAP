from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlparse

from PIL import Image

from .errors import MvpError
from .gemini_packets import GeminiBrowserPacket, verify_packet
from .gemini_session import BrowserTurn
from .jsonio import dump_json, load_json
from .models import CriticReviewDocument
from .workspace import assert_inside_run

if TYPE_CHECKING:
    from .gemini_web import GeminiUltraProfileBinding

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise MvpError(f"cannot hash operator file: {path}") from exc
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class OperatorPolicy:
    model_label: str
    mode_label: str
    plan_token: str
    minimum_session_seconds: float
    max_turns: int = 6

    @classmethod
    def required(cls) -> OperatorPolicy:
        return cls("3.7 Flash", "Tư duy mở rộng", "Ultra", 3.0, 6)


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
    turns: tuple[BrowserTurn, ...] = ()
    ledger_signature: str = ""


class BrowserSessionResult(Protocol):
    observation: BrowserObservation
    response: str
    turns: tuple[BrowserTurn, ...]


SessionRunner = Callable[
    [OperatorRequest, GeminiBrowserPacket],
    BrowserSessionResult | tuple[BrowserObservation, str],
]


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
                    raw["turns"] = tuple(
                        BrowserTurn(**turn) for turn in raw.get("turns", ())
                    )
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


def _parse_single_json_object(text: str) -> dict[str, Any]:
    candidate = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, re.DOTALL | re.IGNORECASE)
    if fenced:
        candidate = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    try:
        value, end = decoder.raw_decode(candidate)
    except json.JSONDecodeError as exc:
        raise MvpError("Gemini response is not valid JSON") from exc
    trailing = candidate[end:].strip()
    ui_suffix_lines = tuple(line.strip() for line in trailing.splitlines() if line.strip())
    known_ui_suffix = bool(ui_suffix_lines) and all(
        re.fullmatch(
            r"(?:json|copy(?: code)?|sao chép(?: mã)?|\+\s*\d+)",
            line,
            re.IGNORECASE,
        )
        for line in ui_suffix_lines
    )
    if trailing and not known_ui_suffix:
        raise MvpError("Gemini response must contain exactly one JSON object")
    if not isinstance(value, dict):
        raise MvpError("Gemini response JSON root must be an object")
    return value


def _safe_run_file(path: Path, run_dir: Path, label: str) -> Path:
    if path.is_symlink():
        raise MvpError(f"operator {label} may not be a symlink")
    try:
        safe = assert_inside_run(path, run_dir)
    except (MvpError, OSError) as exc:
        raise MvpError(f"operator {label} is outside run") from exc
    if not safe.is_file():
        raise MvpError(f"operator {label} is missing")
    return safe


@dataclass(frozen=True, slots=True)
class GeminiWebOperator:
    run_dir: Path
    binding: GeminiUltraProfileBinding
    ledger: OperatorLedger
    session_runner: SessionRunner
    policy: OperatorPolicy
    operator_build_sha256: str

    def run(
        self,
        request: OperatorRequest,
        packet: GeminiBrowserPacket,
    ) -> OperatorReceipt:
        run_dir = self.run_dir.resolve()
        if request.run_id != run_dir.name or request.phase != packet.phase:
            raise MvpError("operator request belongs to another run or phase")
        expected = issue_request(
            request.run_id,
            request.phase,
            request.artifact_sha256,
            request.packet_sha256,
            nonce=request.nonce,
            issued_at=request.issued_at,
        )
        if expected.request_sha256 != request.request_sha256:
            raise MvpError("operator request hash is invalid")
        if not _SHA256.fullmatch(self.operator_build_sha256):
            raise MvpError("operator build hash is invalid")
        verify_packet(packet, run_dir)
        if packet.packet_sha256 != request.packet_sha256:
            raise MvpError("operator packet does not match request")
        media = _safe_run_file(Path(packet.media_path), run_dir, "packet media")
        if _sha256_file(media) != request.artifact_sha256:
            raise MvpError("operator artifact hash does not match request")

        phase_dir = run_dir / "gemini_web" / packet.phase.casefold()
        phase_dir.mkdir(parents=True, exist_ok=True)
        request_path = phase_dir / "operator_request.json"
        dump_json(request_path, request)

        session_result = self.session_runner(request, packet)
        if isinstance(session_result, tuple):
            observation, dom_text = session_result
            turns: tuple[BrowserTurn, ...] = ()
        else:
            observation = session_result.observation
            dom_text = session_result.response
            turns = session_result.turns
        if observation.account_sha256 != self.binding.account_sha256:
            raise MvpError("Gemini observation does not match bound account")
        if observation.account_hint != self.binding.account_hint:
            raise MvpError("Gemini observation account hint does not match binding")
        screenshot = _safe_run_file(
            Path(observation.screenshot_path), run_dir, "session screenshot"
        )

        raw_path = phase_dir / "raw_response.json"
        raw_path.write_text(
            json.dumps(
                {
                    "run_id": request.run_id,
                    "phase": request.phase,
                    "conversation_url": observation.conversation_url,
                    "captured_at": datetime.now(UTC).isoformat(),
                    "dom_text": dom_text,
                    "turns": [asdict(turn) for turn in turns],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        critic_path = phase_dir / f"critic_{packet.phase.casefold()}.json"
        payload = _parse_single_json_object(dom_text)
        critic_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            review = load_json(critic_path, CriticReviewDocument)
            expected_phase = "SCRIPT" if packet.phase == "SCRIPT" else "VIDEO"
            if review.phase != expected_phase:
                raise MvpError("Gemini critic phase does not match packet")
            review_ids = tuple(item.beat_id for item in review.beat_reviews)
            if len(review_ids) != len(set(review_ids)) or set(review_ids) != set(
                packet.beat_ids
            ):
                raise MvpError("Gemini critic must cover every packet beat exactly once")
            validate_browser_evidence(
                observation,
                self.policy,
                raw_response=raw_path,
                critic=critic_path,
            )
        except Exception:
            critic_path.unlink(missing_ok=True)
            raise

        unsigned = OperatorReceipt(
            run_id=request.run_id,
            phase=request.phase,
            nonce=request.nonce,
            request_sha256=request.request_sha256,
            artifact_sha256=request.artifact_sha256,
            packet_sha256=request.packet_sha256,
            observation=observation,
            screenshot_sha256=_sha256_file(screenshot),
            raw_response_path=str(raw_path.resolve()),
            raw_response_sha256=_sha256_file(raw_path),
            critic_path=str(critic_path.resolve()),
            critic_sha256=_sha256_file(critic_path),
            operator_build_sha256=self.operator_build_sha256,
            turns=turns,
        )
        signature = self.ledger.append(unsigned)
        signed = replace(unsigned, ledger_signature=signature)
        dump_json(phase_dir / "operator_receipt.json", signed)
        return signed
