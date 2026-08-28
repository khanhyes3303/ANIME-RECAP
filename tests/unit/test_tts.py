from __future__ import annotations

import base64
import wave
from pathlib import Path

import httpx
import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import (
    Claim,
    NarrationCue,
    NarrationSpan,
    NarrationSpanDocument,
    ScriptDocument,
    SpanSourceRange,
)
from anime_review_mvp.tts import (
    ProviderChunkResult,
    ProviderSynthesisResult,
    TikTokCapCutProvider,
    default_policy,
    default_profile,
    normalize_speech_text,
    plan_chunks,
    synthesize_script,
    synthesize_spans,
)


def test_vietnamese_chunks_reconstruct_exact_text() -> None:
    text = "Cậu này vừa vào lớp, đã bị dí KPI. Đúng là hết cứu!"
    chunks = plan_chunks(text, character_ceiling=30)
    assert " ".join(chunks) == normalize_speech_text(text)
    assert all(len(chunk) <= 30 for chunk in chunks)


def test_provider_retries_503_and_keeps_exact_voice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANIME_RECAP_TIKTOK_SESSION", "opaque")
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        assert request.url.params["text_speaker"] == "BV074_streaming"
        if attempts == 1:
            return httpx.Response(503)
        encoded = base64.b64encode(b"mp3-data").decode("ascii")
        return httpx.Response(200, json={"status_code": 0, "data": {"v_str": encoded}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = TikTokCapCutProvider(client).synthesize(
        ("xin chào",), default_profile(), default_policy()
    )

    assert result.chunks[0].attempts == 2
    assert dict(result.safe_metadata)["voice_id"] == "BV074_streaming"


def test_missing_session_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANIME_RECAP_TIKTOK_SESSION", raising=False)
    with pytest.raises(MvpError, match="ANIME_RECAP_TIKTOK_SESSION"):
        TikTokCapCutProvider().synthesize(
            ("xin chào",), default_profile(), default_policy()
        )


class FakeProvider:
    def synthesize(
        self, chunks: tuple[str, ...], profile: object, policy: object
    ) -> ProviderSynthesisResult:
        del profile, policy
        return ProviderSynthesisResult(
            tuple(ProviderChunkResult(chunk.encode("utf-8"), 1) for chunk in chunks),
            (("provider", "fake"), ("voice_id", "BV074_streaming")),
        )


def _fake_converter(source: Path, output: Path) -> None:
    assert source.read_bytes()
    with wave.open(str(output), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(24_000)
        target.writeframes(b"\0\0" * 2_400)


def test_synthesize_script_creates_cue_audio_and_gapless_manifest(tmp_path: Path) -> None:
    script = ScriptDocument(
        (
            NarrationCue("cue-001", "Xin chào.", ("c1",), ("e1",), True),
            NarrationCue("cue-002", "Tạm biệt.", ("c2",), ("e2",), True),
        )
    )

    manifest = synthesize_script(
        script, tmp_path, provider=FakeProvider(), converter=_fake_converter
    )

    assert [cue.duration_ms for cue in manifest.cues] == [100, 100]
    assert manifest.voice_id == "BV074_streaming"
    with wave.open(manifest.narration_wav_path, "rb") as narration:
        assert narration.getnframes() == 4_800
        assert narration.getframerate() == 24_000
    assert (tmp_path / "tts_manifest.json").exists()


def test_synthesize_spans_creates_one_wav_per_locked_span(tmp_path: Path) -> None:
    document = NarrationSpanDocument(
        spans=(
            NarrationSpan(
                "span-001",
                "Jiro lao qua cổng.",
                ("claim-001",),
                ("event-001",),
                ("Jiro",),
                "Jiro chạy qua cổng.",
                (
                    SpanSourceRange(
                        "range-001",
                        0,
                        100,
                        "scene-001",
                        "beat-001",
                        ("shot-001",),
                        ("event-001",),
                        True,
                    ),
                ),
            ),
        ),
        claims=(Claim("claim-001", "ACTION", "Jiro runs.", ("event-001",)),),
        owner="CODEX",
    )

    manifest = synthesize_spans(
        document,
        tmp_path,
        provider=FakeProvider(),
        converter=_fake_converter,
    )

    assert [item.span_id for item in manifest.spans] == ["span-001"]
    assert Path(manifest.spans[0].wav_path).name == "span-001.wav"
    assert manifest.spans[0].duration_ms == 100
    assert (tmp_path / "span_tts_manifest.json").is_file()
