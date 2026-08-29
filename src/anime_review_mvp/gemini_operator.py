from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
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
