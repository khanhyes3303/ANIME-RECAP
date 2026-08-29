from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from anime_review_mvp.errors import MvpError
from anime_review_mvp.gemini_operator import (
    BrowserObservation,
    OperatorPolicy,
    validate_browser_evidence,
)


def _valid_screenshot(path: Path) -> Path:
    Image.effect_noise((1280, 720), 64).convert("RGB").save(path)
    return path


def _valid_evidence(tmp_path: Path) -> tuple[BrowserObservation, Path, Path]:
    screenshot = _valid_screenshot(tmp_path / "session.png")
    raw = tmp_path / "raw_response.json"
    critic = tmp_path / "critic_script.json"
    raw.write_text(
        '{"dom_text":"Gemini answer","conversation_url":"https://gemini.google.com/app/abc"}',
        encoding="utf-8",
    )
    critic.write_text('{"overall_verdict":"MATCH"}', encoding="utf-8")
    return (
        BrowserObservation(
            account_sha256="a" * 64,
            account_hint="n***@gmail.com",
            plan_label="Google AI Ultra",
            model_label="3.7 Flash",
            mode_label="Tư duy mở rộng",
            conversation_url="https://gemini.google.com/app/abc",
            chrome_pid=123,
            screenshot_path=str(screenshot),
            started_at="2026-08-29T21:00:00+07:00",
            finished_at="2026-08-29T21:00:10+07:00",
        ),
        raw,
        critic,
    )


def test_rejects_the_exact_fabricated_antigravity_evidence(tmp_path: Path) -> None:
    """A black fake session, obsolete model, and self-authored response cannot pass."""
    screenshot = tmp_path / "session.png"
    Image.new("RGB", (1280, 720), "black").save(screenshot)
    critic = tmp_path / "critic_script.json"
    raw = tmp_path / "response.txt"
    critic.write_text('{"overall_verdict":"MATCH"}', encoding="utf-8")
    raw.write_bytes(critic.read_bytes())
    observation = BrowserObservation(
        account_sha256="a" * 64,
        account_hint="n***@gmail.com",
        plan_label="Google AI Ultra",
        model_label="Gemini 2.5 Pro Ultra",
        mode_label="Tư duy mở rộng",
        conversation_url="https://gemini.google.com/app/abc",
        chrome_pid=123,
        screenshot_path=str(screenshot),
        started_at="2026-08-29T21:00:00+07:00",
        finished_at="2026-08-29T21:00:01+07:00",
    )

    with pytest.raises(MvpError, match="3.7 Flash|screenshot|raw response"):
        validate_browser_evidence(
            observation,
            OperatorPolicy.required(),
            raw_response=raw,
            critic=critic,
        )


def test_accepts_realistic_browser_evidence(tmp_path: Path) -> None:
    observation, raw, critic = _valid_evidence(tmp_path)

    validate_browser_evidence(
        observation,
        OperatorPolicy.required(),
        raw_response=raw,
        critic=critic,
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("model_label", "Gemini 2.5 Pro Ultra", "3.7 Flash"),
        ("mode_label", "Nhanh", "Tư duy mở rộng"),
        ("plan_label", "Google AI Pro", "not Ultra"),
        ("conversation_url", "https://gemini.google.com/app", "real chat"),
        ("chrome_pid", 0, "PID"),
        ("finished_at", "2026-08-29T21:00:01+07:00", "quickly"),
    ),
)
def test_rejects_invalid_session_claims(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    observation, raw, critic = _valid_evidence(tmp_path)

    with pytest.raises(MvpError, match=message):
        validate_browser_evidence(
            replace(observation, **{field: value}),
            OperatorPolicy.required(),
            raw_response=raw,
            critic=critic,
        )


def test_rejects_solid_session_screenshot(tmp_path: Path) -> None:
    observation, raw, critic = _valid_evidence(tmp_path)
    solid = tmp_path / "solid.png"
    Image.new("RGB", (1280, 720), "black").save(solid)

    with pytest.raises(MvpError, match="screenshot"):
        validate_browser_evidence(
            replace(observation, screenshot_path=str(solid)),
            OperatorPolicy.required(),
            raw_response=raw,
            critic=critic,
        )


def test_rejects_raw_response_identical_to_critic(tmp_path: Path) -> None:
    observation, raw, critic = _valid_evidence(tmp_path)
    raw.write_bytes(critic.read_bytes())

    with pytest.raises(MvpError, match="raw response"):
        validate_browser_evidence(
            observation,
            OperatorPolicy.required(),
            raw_response=raw,
            critic=critic,
        )
