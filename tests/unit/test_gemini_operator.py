from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from anime_review_mvp.errors import MvpError
from anime_review_mvp.gemini_operator import (
    BrowserObservation,
    OperatorLedger,
    OperatorPolicy,
    OperatorReceipt,
    OperatorRequest,
    _parse_single_json_object,
    validate_browser_evidence,
    verify_operator_receipt,
)


def _valid_screenshot(path: Path) -> Path:
    Image.effect_noise((1280, 720), 64).convert("RGB").save(path)
    return path


def test_parser_accepts_only_known_gemini_code_block_ui_suffix() -> None:
    response = '{"phase":"VIDEO"}\nJSON\n+ 4'

    assert _parse_single_json_object(response) == {"phase": "VIDEO"}


def test_parser_still_rejects_arbitrary_text_after_json() -> None:
    with pytest.raises(MvpError, match="exactly one JSON object"):
        _parse_single_json_object('{"phase":"VIDEO"}\nignore this trailing prose')


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

    with pytest.raises(MvpError, match="quickly|screenshot|raw response"):
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


def test_accepts_user_selected_account_and_model_without_verification(
    tmp_path: Path,
) -> None:
    observation, raw, critic = _valid_evidence(tmp_path)

    validate_browser_evidence(
        replace(
            observation,
            plan_label="USER_SELECTION_NOT_VERIFIED",
            model_label="USER_SELECTED_NOT_VERIFIED",
            mode_label="USER_SELECTED_NOT_VERIFIED",
        ),
        OperatorPolicy.required(),
        raw_response=raw,
        critic=critic,
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
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


def _operator_request() -> OperatorRequest:
    return OperatorRequest(
        run_id="run-123",
        phase="SCRIPT",
        nonce="nonce-123",
        request_sha256="1" * 64,
        artifact_sha256="2" * 64,
        packet_sha256="3" * 64,
        issued_at="2026-08-29T21:00:00+07:00",
    )


def _operator_receipt(tmp_path: Path) -> OperatorReceipt:
    observation, raw, critic = _valid_evidence(tmp_path)
    return OperatorReceipt(
        run_id="run-123",
        phase="SCRIPT",
        nonce="nonce-123",
        request_sha256="1" * 64,
        artifact_sha256="2" * 64,
        packet_sha256="3" * 64,
        observation=observation,
        screenshot_sha256="4" * 64,
        raw_response_path=str(raw),
        raw_response_sha256="5" * 64,
        critic_path=str(critic),
        critic_sha256="6" * 64,
        operator_build_sha256="7" * 64,
    )


def test_receipt_without_matching_signed_ledger_entry_is_rejected(tmp_path: Path) -> None:
    ledger = OperatorLedger(tmp_path / "operator-ledger.jsonl", b"k" * 32)

    with pytest.raises(MvpError, match="ledger"):
        verify_operator_receipt(
            _operator_receipt(tmp_path),
            ledger,
            expected_request=_operator_request(),
        )


def test_signed_ledger_entry_verifies_exact_receipt(tmp_path: Path) -> None:
    ledger = OperatorLedger(tmp_path / "operator-ledger.jsonl", b"k" * 32)
    unsigned = _operator_receipt(tmp_path)
    signed = replace(unsigned, ledger_signature=ledger.append(unsigned))

    assert verify_operator_receipt(
        signed,
        ledger,
        expected_request=_operator_request(),
    ) == signed


def test_reused_nonce_is_rejected_even_when_both_entries_are_signed(tmp_path: Path) -> None:
    ledger = OperatorLedger(tmp_path / "operator-ledger.jsonl", b"k" * 32)
    unsigned = _operator_receipt(tmp_path)
    first = replace(unsigned, ledger_signature=ledger.append(unsigned))
    ledger.append(replace(unsigned, critic_sha256="8" * 64))

    with pytest.raises(MvpError, match="unique ledger"):
        verify_operator_receipt(first, ledger, expected_request=_operator_request())


def test_tampered_ledger_signature_is_rejected(tmp_path: Path) -> None:
    ledger_path = tmp_path / "operator-ledger.jsonl"
    ledger = OperatorLedger(ledger_path, b"k" * 32)
    unsigned = _operator_receipt(tmp_path)
    signed = replace(unsigned, ledger_signature=ledger.append(unsigned))
    ledger_path.write_text(
        ledger_path.read_text(encoding="utf-8").replace(signed.ledger_signature, "0" * 64),
        encoding="utf-8",
    )

    with pytest.raises(MvpError, match="signature"):
        verify_operator_receipt(signed, ledger, expected_request=_operator_request())


def test_receipt_for_different_request_is_rejected(tmp_path: Path) -> None:
    ledger = OperatorLedger(tmp_path / "operator-ledger.jsonl", b"k" * 32)
    unsigned = _operator_receipt(tmp_path)
    signed = replace(unsigned, ledger_signature=ledger.append(unsigned))

    with pytest.raises(MvpError, match="request"):
        verify_operator_receipt(
            signed,
            ledger,
            expected_request=replace(_operator_request(), packet_sha256="9" * 64),
        )
