from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
import shutil
import subprocess
import unicodedata
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx

from .errors import MvpError
from .jsonio import dump_json
from .models import (
    AtomicStoryboard,
    AtomicTtsBeat,
    AtomicTtsManifest,
    NarrationSpanDocument,
    ScriptDocument,
    SpanTts,
    SpanTtsManifest,
    TtsCue,
    TtsManifest,
    TtsCacheStats,
)

ENDPOINT = "https://api16-normal-v6.tiktokv.com/media/api/text/speech/invoke/"
USER_AGENT = "com.zhiliaoapp.musically/2022600030 (Linux; U; Android 13; vi_VN)"


@dataclass(frozen=True, slots=True)
class VoiceProfile:
    provider: str
    voice_id: str
    language: str
    provider_audio_format: str
    analysis_codec: str
    analysis_sample_rate: int
    analysis_channels: int
    credential_env_name: str


@dataclass(frozen=True, slots=True)
class SpeechPolicy:
    character_ceiling: int
    max_attempts: int
    request_timeout_milliseconds: int
    retryable_http_statuses: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ProviderChunkResult:
    audio: bytes
    attempts: int


@dataclass(frozen=True, slots=True)
class ProviderSynthesisResult:
    chunks: tuple[ProviderChunkResult, ...]
    safe_metadata: tuple[tuple[str, str], ...]


class TtsProvider(Protocol):
    def synthesize(
        self,
        chunks: tuple[str, ...],
        profile: VoiceProfile,
        policy: SpeechPolicy,
    ) -> ProviderSynthesisResult: ...


def default_profile() -> VoiceProfile:
    return VoiceProfile(
        provider="tiktok-capcut",
        voice_id="BV074_streaming",
        language="vi-VN",
        provider_audio_format="mp3",
        analysis_codec="pcm_s16le",
        analysis_sample_rate=24_000,
        analysis_channels=1,
        credential_env_name="ANIME_RECAP_TIKTOK_SESSION",
    )


def default_policy() -> SpeechPolicy:
    return SpeechPolicy(
        character_ceiling=150,
        max_attempts=3,
        request_timeout_milliseconds=30_000,
        retryable_http_statuses=(429, 500, 502, 503, 504),
    )


def normalize_speech_text(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        raise MvpError("speech text must not be empty")
    return normalized


def plan_chunks(text: str, *, character_ceiling: int = 150) -> tuple[str, ...]:
    if character_ceiling < 1:
        raise MvpError("speech chunk ceiling must be positive")
    normalized = normalize_speech_text(text)
    sentences = _units(normalized, r"(?<=[.!?…])\s+")
    refined = tuple(
        chunk for sentence in sentences for chunk in _refine(sentence, character_ceiling)
    )
    chunks = _pack(refined, character_ceiling)
    if (
        not chunks
        or any(len(chunk) > character_ceiling for chunk in chunks)
        or " ".join(chunks) != normalized
    ):
        raise MvpError("speech chunking did not reconstruct exact normalized text")
    return chunks


def _units(text: str, pattern: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in re.split(pattern, text) if part.strip())


def _refine(unit: str, ceiling: int) -> tuple[str, ...]:
    if len(unit) <= ceiling:
        return (unit,)
    clauses = _units(unit, r"(?<=[,;:])\s+|\s+(?=[–—])|(?<=[–—])\s+")
    if len(clauses) > 1:
        return tuple(chunk for clause in clauses for chunk in _refine(clause, ceiling))
    words = unit.split()
    if any(len(word) > ceiling for word in words):
        raise MvpError("speech text contains an unsplittable oversized token")
    return _pack(tuple(words), ceiling)


def _pack(units: Sequence[str], ceiling: int) -> tuple[str, ...]:
    result: list[str] = []
    current = ""
    for unit in units:
        candidate = unit if not current else f"{current} {unit}"
        if len(candidate) <= ceiling:
            current = candidate
        else:
            if current:
                result.append(current)
            current = unit
    if current:
        result.append(current)
    return tuple(result)


class TikTokCapCutProvider:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def synthesize(
        self,
        chunks: tuple[str, ...],
        profile: VoiceProfile,
        policy: SpeechPolicy,
    ) -> ProviderSynthesisResult:
        credential = os.environ.get(profile.credential_env_name, "")
        if not credential:
            raise MvpError(
                "required TTS credential environment variable is absent: "
                f"{profile.credential_env_name}"
            )
        owned = self._client is None
        client = self._client or httpx.Client(
            timeout=policy.request_timeout_milliseconds / 1_000
        )
        try:
            results = tuple(
                self._one(client, text, credential, profile, policy) for text in chunks
            )
        finally:
            if owned:
                client.close()
        return ProviderSynthesisResult(
            results,
            (
                ("provider", profile.provider),
                ("voice_id", profile.voice_id),
                ("endpoint_host", "api16-normal-v6.tiktokv.com"),
            ),
        )

    @staticmethod
    def _one(
        client: httpx.Client,
        text: str,
        credential: str,
        profile: VoiceProfile,
        policy: SpeechPolicy,
    ) -> ProviderChunkResult:
        for attempt in range(1, policy.max_attempts + 1):
            try:
                response = client.post(
                    ENDPOINT,
                    params={
                        "text_speaker": profile.voice_id,
                        "req_text": text,
                        "speaker_map_type": "0",
                        "aid": "1233",
                    },
                    headers={
                        "User-Agent": USER_AGENT,
                        "Cookie": f"sessionid={credential}",
                    },
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == policy.max_attempts:
                    raise MvpError("TTS provider transport failed after retries") from exc
                continue
            if response.status_code in (401, 403):
                raise MvpError("TTS provider authentication rejected")
            if response.status_code in policy.retryable_http_statuses:
                if attempt == policy.max_attempts:
                    raise MvpError("TTS provider exhausted retryable responses")
                continue
            if response.status_code != 200:
                raise MvpError(f"TTS provider HTTP failure: {response.status_code}")
            try:
                payload = response.json()
                if payload.get("status_code") != 0:
                    raise MvpError("TTS provider returned a non-success status")
                audio = base64.b64decode(payload["data"]["v_str"], validate=True)
            except (KeyError, TypeError, ValueError, binascii.Error) as exc:
                raise MvpError("TTS provider returned malformed audio") from exc
            if not audio:
                raise MvpError("TTS provider returned empty audio")
            return ProviderChunkResult(audio, attempt)
        raise AssertionError("unreachable bounded retry loop")


Converter = Callable[[Path, Path], None]


def _convert_mp3_to_wav(source: Path, output: Path) -> None:
    result = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-acodec",
            "pcm_s16le",
            "-ar",
            "24000",
            "-ac",
            "1",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise MvpError(f"cannot convert TTS audio: {result.stderr.strip()}")


def _wav_duration_ms(path: Path) -> int:
    try:
        with wave.open(str(path), "rb") as source:
            if (
                source.getnchannels() != 1
                or source.getsampwidth() != 2
                or source.getframerate() != 24_000
            ):
                raise MvpError("TTS WAV must be PCM s16le, 24000 Hz, mono")
            return round(source.getnframes() * 1_000 / source.getframerate())
    except (OSError, wave.Error) as exc:
        raise MvpError(f"cannot read TTS WAV: {path}") from exc


def _concatenate_wavs(paths: list[Path], output: Path) -> None:
    with wave.open(str(output), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(24_000)
        for path in paths:
            with wave.open(str(path), "rb") as source:
                if source.getparams()[:3] != (1, 2, 24_000):
                    raise MvpError("all cue WAV files must share the TTS audio format")
                target.writeframes(source.readframes(source.getnframes()))


def synthesize_script(
    script: ScriptDocument,
    output_dir: Path,
    *,
    provider: TtsProvider | None = None,
    converter: Converter = _convert_mp3_to_wav,
) -> TtsManifest:
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = default_profile()
    policy = default_policy()
    engine = provider or TikTokCapCutProvider()
    cue_results: list[TtsCue] = []
    wav_paths: list[Path] = []
    for cue in script.cues:
        synthesis = engine.synthesize(
            plan_chunks(cue.text, character_ceiling=policy.character_ceiling),
            profile,
            policy,
        )
        mp3_path = output_dir / f"{cue.cue_id}.mp3"
        wav_path = output_dir / f"{cue.cue_id}.wav"
        mp3_path.write_bytes(b"".join(chunk.audio for chunk in synthesis.chunks))
        converter(mp3_path, wav_path)
        duration_ms = _wav_duration_ms(wav_path)
        cue_results.append(
            TtsCue(cue.cue_id, str(mp3_path), str(wav_path), duration_ms)
        )
        wav_paths.append(wav_path)

    narration_path = output_dir / "narration.wav"
    _concatenate_wavs(wav_paths, narration_path)
    manifest = TtsManifest(
        cues=tuple(cue_results),
        narration_wav_path=str(narration_path),
        provider=profile.provider,
        voice_id=profile.voice_id,
    )
    dump_json(output_dir / "tts_manifest.json", manifest)
    return manifest


def synthesize_spans(
    document: NarrationSpanDocument,
    output_dir: Path,
    *,
    provider: TtsProvider | None = None,
    converter: Converter = _convert_mp3_to_wav,
) -> SpanTtsManifest:
    output_dir.mkdir(parents=True, exist_ok=True)
    profile = default_profile()
    policy = default_policy()
    engine = provider or TikTokCapCutProvider()
    results: list[SpanTts] = []
    wav_paths: list[Path] = []
    for span in document.spans:
        synthesis = engine.synthesize(
            plan_chunks(span.text, character_ceiling=policy.character_ceiling),
            profile,
            policy,
        )
        mp3_path = output_dir / f"{span.span_id}.mp3"
        wav_path = output_dir / f"{span.span_id}.wav"
        mp3_path.write_bytes(b"".join(chunk.audio for chunk in synthesis.chunks))
        converter(mp3_path, wav_path)
        duration_ms = _wav_duration_ms(wav_path)
        results.append(SpanTts(span.span_id, str(mp3_path), str(wav_path), duration_ms))
        wav_paths.append(wav_path)

    narration_path = output_dir / "narration.wav"
    _concatenate_wavs(wav_paths, narration_path)
    manifest = SpanTtsManifest(
        spans=tuple(results),
        narration_wav_path=str(narration_path),
        provider=profile.provider,
        voice_id=profile.voice_id,
    )
    dump_json(output_dir / "span_tts_manifest.json", manifest)
    return manifest


def _atomic_tts_cache_key(text: str, profile: VoiceProfile, policy_version: str) -> str:
    normalized = normalize_speech_text(text)
    raw = "\0".join((normalized, profile.provider, profile.voice_id, policy_version))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def synthesize_atomic_beats(
    storyboard: AtomicStoryboard,
    output_dir: Path,
    cache_dir: Path,
    *,
    provider: TtsProvider | None = None,
    converter: Converter = _convert_mp3_to_wav,
) -> AtomicTtsManifest:
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    profile = default_profile()
    policy = default_policy()
    engine = provider or TikTokCapCutProvider()
    results: list[AtomicTtsBeat] = []
    wav_paths: list[Path] = []
    hits = 0
    misses = 0

    for beat in storyboard.beats:
        if beat.status != "LOCKED":
            raise MvpError(f"atomic TTS requires LOCKED beat: {beat.beat_id}")
        cache_key = _atomic_tts_cache_key(
            beat.narration_text,
            profile,
            storyboard.policy_version,
        )
        entry = cache_dir / cache_key
        cached_mp3 = entry / "audio.mp3"
        cached_wav = entry / "audio.wav"
        output_mp3 = output_dir / f"{beat.beat_id}.mp3"
        output_wav = output_dir / f"{beat.beat_id}.wav"
        if cached_mp3.is_file() and cached_wav.is_file():
            duration_ms = _wav_duration_ms(cached_wav)
            hits += 1
        else:
            entry.mkdir(parents=True, exist_ok=True)
            synthesis = engine.synthesize(
                plan_chunks(beat.narration_text, character_ceiling=policy.character_ceiling),
                profile,
                policy,
            )
            temp_mp3 = entry / "audio.tmp.mp3"
            temp_wav = entry / "audio.tmp.wav"
            temp_mp3.write_bytes(b"".join(chunk.audio for chunk in synthesis.chunks))
            converter(temp_mp3, temp_wav)
            duration_ms = _wav_duration_ms(temp_wav)
            os.replace(temp_mp3, cached_mp3)
            os.replace(temp_wav, cached_wav)
            misses += 1
        shutil.copy2(cached_mp3, output_mp3)
        shutil.copy2(cached_wav, output_wav)
        results.append(
            AtomicTtsBeat(
                beat.beat_id,
                str(output_mp3),
                str(output_wav),
                duration_ms,
                cache_key,
            )
        )
        wav_paths.append(output_wav)

    narration_path = output_dir / "narration.wav"
    _concatenate_wavs(wav_paths, narration_path)
    manifest = AtomicTtsManifest(
        tuple(results),
        str(narration_path),
        profile.provider,
        profile.voice_id,
        storyboard.policy_version,
        TtsCacheStats(hits, misses),
    )
    dump_json(output_dir / "atomic_tts_manifest.json", manifest)
    return manifest
