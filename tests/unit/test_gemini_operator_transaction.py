from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from anime_review_mvp.errors import MvpError
from anime_review_mvp.gemini_operator import (
    BrowserObservation,
    GeminiWebOperator,
    OperatorLedger,
    OperatorPolicy,
    issue_request,
    verify_operator_receipt,
)
from anime_review_mvp.gemini_packets import GeminiBrowserPacket
from anime_review_mvp.gemini_selenium import BrowserConversationResult, BrowserTurn
from anime_review_mvp.gemini_web import (
    GeminiUltraProfileBinding,
    load_operator_verified_review,
    sha256_file,
)
from anime_review_mvp.models import CriticReviewDocument


def _packet(run: Path) -> GeminiBrowserPacket:
    packet_dir = run / "gemini_web" / "script" / "operator_packet"
    packet_dir.mkdir(parents=True)
    media = packet_dir / "script_evidence.mp4"
    prompt = packet_dir / "prompt.txt"
    supplemental = packet_dir / "storyboard.json"
    media.write_bytes(b"video evidence")
    prompt.write_text("Return JSON", encoding="utf-8")
    supplemental.write_text("{}", encoding="utf-8")
    files = (media, supplemental, prompt)
    manifest = packet_dir / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "phase": "SCRIPT",
                "beat_ids": ["beat-001"],
                "files": [
                    {"path": str(path.resolve()), "sha256": sha256_file(path)}
                    for path in files
                ],
                "excluded_regions": [],
            }
        ),
        encoding="utf-8",
    )
    return GeminiBrowserPacket(
        "SCRIPT",
        str(media.resolve()),
        str(manifest.resolve()),
        str(prompt.resolve()),
        tuple(str(path.resolve()) for path in (media, supplemental, manifest)),
        sha256_file(manifest),
        ("beat-001",),
    )


def _response(*, beat_id: str = "beat-001") -> str:
    return json.dumps(
        {
            "phase": "SCRIPT",
            "producer_context_id": "producer-01",
            "critic_context_id": "gemini-web-critic-01",
            "beat_reviews": [
                {
                    "beat_id": beat_id,
                    "finding_codes": [],
                    "evidence_refs": ["beat-001@00:00:01.000"],
                    "observed_visual": "Jiro đứng trước con mèo.",
                    "narration_summary": "Jiro nhìn con mèo.",
                    "sync_verdict": "MATCH",
                    "note": "Hình và lời khớp.",
                }
            ],
        },
        ensure_ascii=False,
    )


def _runner(run: Path, response: str):
    def execute(request, packet):
        screenshot = run / "gemini_web" / "script" / "screenshots" / "session.png"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        Image.effect_noise((1280, 720), 64).convert("RGB").save(screenshot)
        observation = BrowserObservation(
            account_sha256="a" * 64,
            account_hint="k***@gmail.com",
            plan_label="Google AI Ultra",
            model_label="3.7 Flash",
            mode_label="Tư duy mở rộng",
            conversation_url="https://gemini.google.com/app/chat-123",
            chrome_pid=321,
            screenshot_path=str(screenshot.resolve()),
            started_at="2026-08-29T21:00:00+07:00",
            finished_at="2026-08-29T21:00:10+07:00",
        )
        run.joinpath("gemini_web", "session.json").write_text(
            json.dumps(
                {
                    "run_id": run.name,
                    "conversation_url": observation.conversation_url,
                }
            ),
            encoding="utf-8",
        )
        return BrowserConversationResult(
            observation,
            response,
            (
                BrowserTurn(
                    1,
                    "1" * 64,
                    "2" * 64,
                    observation.conversation_url,
                    observation.started_at,
                    observation.finished_at,
                ),
            ),
        )

    return execute


def _operator(run: Path, response: str, ledger: OperatorLedger) -> GeminiWebOperator:
    return GeminiWebOperator(
        run_dir=run,
        binding=GeminiUltraProfileBinding("a" * 64, "k***@gmail.com"),
        ledger=ledger,
        session_runner=_runner(run, response),
        policy=OperatorPolicy.required(),
        operator_build_sha256="b" * 64,
    )


def test_operator_parses_real_response_then_signs_ledger(tmp_path: Path) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-123"
    packet = _packet(run)
    request = issue_request(
        run.name,
        packet.phase,
        sha256_file(Path(packet.media_path)),
        packet.packet_sha256,
        nonce="nonce-123",
    )
    ledger = OperatorLedger(tmp_path / ".local" / "operator-ledger.jsonl", b"k" * 32)

    receipt = _operator(run, _response(), ledger).run(request, packet)

    assert verify_operator_receipt(receipt, ledger, expected_request=request) == receipt
    raw = json.loads(Path(receipt.raw_response_path).read_text(encoding="utf-8"))
    critic = json.loads(Path(receipt.critic_path).read_text(encoding="utf-8"))
    assert raw["dom_text"] == _response()
    assert raw["turns"][0]["index"] == 1
    assert receipt.turns[0].conversation_url.endswith("chat-123")
    assert raw != critic
    assert critic["beat_reviews"][0]["beat_id"] == "beat-001"

    loaded = load_operator_verified_review(
        run,
        "SCRIPT",
        CriticReviewDocument,
        ledger=ledger,
    )
    assert loaded.beat_reviews[0].beat_id == "beat-001"


@pytest.mark.parametrize(
    ("response", "message"),
    (
        ("not JSON", "JSON"),
        (_response() + "\n" + _response(), "exactly one JSON"),
        (_response(beat_id="beat-999"), "every packet beat"),
    ),
)
def test_operator_rejects_invalid_response_without_ledger_entry(
    tmp_path: Path, response: str, message: str
) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-123"
    packet = _packet(run)
    request = issue_request(
        run.name,
        packet.phase,
        sha256_file(Path(packet.media_path)),
        packet.packet_sha256,
        nonce="nonce-123",
    )
    ledger_path = tmp_path / ".local" / "operator-ledger.jsonl"
    ledger = OperatorLedger(ledger_path, b"k" * 32)

    with pytest.raises(MvpError, match=message):
        _operator(run, response, ledger).run(request, packet)

    assert not ledger_path.exists()


def test_operator_rejects_tampered_packet_before_browser(tmp_path: Path) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-123"
    packet = _packet(run)
    request = issue_request(
        run.name,
        packet.phase,
        sha256_file(Path(packet.media_path)),
        packet.packet_sha256,
        nonce="nonce-123",
    )
    Path(packet.media_path).write_bytes(b"tampered")
    called = False

    def session_runner(request, packet):
        nonlocal called
        called = True
        raise AssertionError("browser must not open")

    operator = GeminiWebOperator(
        run_dir=run,
        binding=GeminiUltraProfileBinding("a" * 64, "k***@gmail.com"),
        ledger=OperatorLedger(tmp_path / "ledger.jsonl", b"k" * 32),
        session_runner=session_runner,
        policy=OperatorPolicy.required(),
        operator_build_sha256="b" * 64,
    )

    with pytest.raises(MvpError, match="packet file hash"):
        operator.run(request, packet)

    assert called is False


def test_operator_rejects_account_observation_not_matching_binding(tmp_path: Path) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-123"
    packet = _packet(run)
    request = issue_request(
        run.name,
        packet.phase,
        sha256_file(Path(packet.media_path)),
        packet.packet_sha256,
        nonce="nonce-123",
    )
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = OperatorLedger(ledger_path, b"k" * 32)
    operator = _operator(run, _response(), ledger)
    original_runner = operator.session_runner

    def wrong_account(request, packet):
        observation, response = original_runner(request, packet)
        return replace(observation, account_sha256="c" * 64), response

    operator = replace(operator, session_runner=wrong_account)

    with pytest.raises(MvpError, match="bound account"):
        operator.run(request, packet)

    assert not ledger_path.exists()


@pytest.mark.parametrize("target", ("critic", "raw", "screenshot", "packet"))
def test_verified_loader_rejects_any_tampered_operator_artifact(
    tmp_path: Path, target: str
) -> None:
    run = tmp_path / "Tam_dang_xu_ly" / "run-123"
    packet = _packet(run)
    request = issue_request(
        run.name,
        packet.phase,
        sha256_file(Path(packet.media_path)),
        packet.packet_sha256,
        nonce="nonce-123",
    )
    ledger = OperatorLedger(tmp_path / "ledger.jsonl", b"k" * 32)
    receipt = _operator(run, _response(), ledger).run(request, packet)
    targets = {
        "critic": Path(receipt.critic_path),
        "raw": Path(receipt.raw_response_path),
        "screenshot": Path(receipt.observation.screenshot_path),
        "packet": Path(packet.manifest_path),
    }
    targets[target].write_bytes(targets[target].read_bytes() + b"tampered")

    with pytest.raises(MvpError, match="hash|packet"):
        load_operator_verified_review(
            run,
            "SCRIPT",
            CriticReviewDocument,
            ledger=ledger,
        )
