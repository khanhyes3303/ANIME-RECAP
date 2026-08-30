from __future__ import annotations

import wave
from dataclasses import replace
from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.situations import (
    CueTtsManifest,
    EvidenceRange,
    NarrationClaim,
    NarrationCue,
    NarrationPlan,
    NarrationUnit,
    SemanticShotUse,
)
from anime_review_mvp.tts import (
    ProviderChunkResult,
    ProviderSynthesisResult,
    synthesize_narration_cues,
    synthesize_situation_units,
    validate_cue_tts_ids,
)


class CountingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def synthesize(
        self, chunks: tuple[str, ...], profile: object, policy: object
    ) -> ProviderSynthesisResult:
        del profile, policy
        self.calls += 1
        return ProviderSynthesisResult(
            tuple(ProviderChunkResult(chunk.encode("utf-8"), 1) for chunk in chunks),
            (("provider", "fake"), ("voice_id", "BV074_streaming")),
        )


def _converter(source: Path, output: Path) -> None:
    assert source.read_bytes()
    with wave.open(str(output), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(24_000)
        target.writeframes(b"\0\0" * 2_400)


def _unit(index: int, text: str) -> NarrationUnit:
    return NarrationUnit(
        unit_id=f"unit-{index:03d}",
        situation_id=f"situation-{index:03d}",
        factual_claims=(f"Sự kiện {index} xảy ra.",),
        narration_text=text,
        bridge_from_previous="" if index == 1 else "Tiếp đó.",
        bridge_to_next="Rồi chuyện khác xảy ra." if index == 1 else "",
        evidence_ranges=(
            EvidenceRange(
                range_id=f"range-{index:03d}",
                situation_id=f"situation-{index:03d}",
                source_start_ms=index * 2_000,
                source_end_ms=index * 2_000 + 1_000,
                shot_ids=(f"shot-{index:03d}",),
                event_ids=(f"event-{index:03d}",),
                transcript_refs=(f"transcript-{index:03d}",),
                frame_refs=(f"frame-{index:03d}",),
                story_fact=f"Sự kiện {index}.",
            ),
        ),
        status="LOCKED",
    )


def _plan(second_text: str = "Câu thứ hai.") -> NarrationPlan:
    return NarrationPlan(
        "LOCAL_EDITOR",
        "situation-v1",
        (_unit(1, "Câu thứ nhất."), _unit(2, second_text)),
    )


def test_tts_cache_only_regenerates_changed_unit(tmp_path: Path) -> None:
    provider = CountingProvider()
    first = synthesize_situation_units(
        _plan(),
        tmp_path / "out-1",
        tmp_path / "cache",
        source_sha256="1" * 64,
        provider=provider,
        converter=_converter,
    )
    second = synthesize_situation_units(
        _plan("Câu thứ hai đã sửa."),
        tmp_path / "out-2",
        tmp_path / "cache",
        source_sha256="1" * 64,
        provider=provider,
        converter=_converter,
    )

    assert first.cache_hits == 0
    assert first.cache_misses == 2
    assert second.cache_hits == 1
    assert second.cache_misses == 1
    assert provider.calls == 3


def test_tts_manifest_is_gapless_and_measured_from_wav(tmp_path: Path) -> None:
    manifest = synthesize_situation_units(
        _plan(),
        tmp_path / "out",
        tmp_path / "cache",
        source_sha256="2" * 64,
        provider=CountingProvider(),
        converter=_converter,
    )

    assert [unit.duration_ms for unit in manifest.units] == [100, 100]
    assert manifest.total_duration_ms == 200
    assert Path(manifest.narration_wav_path).is_file()
    assert (tmp_path / "out" / "situation_tts_manifest.json").is_file()


def test_tts_rejects_unlocked_unit(tmp_path: Path) -> None:
    plan = _plan()
    draft = replace(plan, units=(replace(plan.units[0], status="DRAFT"), plan.units[1]))

    with pytest.raises(MvpError, match="LOCKED"):
        synthesize_situation_units(
            draft,
            tmp_path / "out",
            tmp_path / "cache",
            source_sha256="3" * 64,
            provider=CountingProvider(),
            converter=_converter,
        )


def _v2_plan() -> NarrationPlan:
    semantic_range = replace(
        _unit(1, "unused").evidence_ranges[0],
        semantic_event_id="event-001",
        action_phase="SETUP",
        story_purpose="Jiro về nhà.",
        shot_uses=(SemanticShotUse("shot-001", "event-001", "SETUP", "Jiro về nhà."),),
    )
    cues = (
        NarrationCue(
            "cue-001", "situation-001", "Jiro vừa về nhà.", ("claim-001",),
            2_000, "SETUP", ("transcript-001",), ("frame-001",), ("shot-001",),
            ("Jiro",), ("Jiro",), (), (),
        ),
        NarrationCue(
            "cue-002", "situation-001", "Ông nội đã đứng chờ.", ("claim-002",),
            3_000, "CHARACTER_INTRO", ("transcript-002",), ("frame-002",),
            ("shot-001",), ("Ông nội",), ("Ông nội",), (), (),
        ),
    )
    unit = replace(
        _unit(1, "Jiro vừa về nhà. Ông nội đã đứng chờ."),
        evidence_ranges=(semantic_range,),
        cues=cues,
    )
    claims = (
        NarrationClaim("claim-001", "Jiro về nhà.", ("event-001",)),
        NarrationClaim("claim-002", "Ông nội đứng chờ.", ("event-001",)),
    )
    return NarrationPlan("LOCAL_EDITOR", "situation-v2", (unit,), claims)


def test_v2_tts_synthesizes_each_cue_without_concatenating_narration(
    tmp_path: Path,
) -> None:
    manifest = synthesize_narration_cues(
        _v2_plan(), tmp_path / "tts", tmp_path / "cache",
        source_sha256="a" * 64, provider=CountingProvider(), converter=_converter,
    )
    assert [cue.cue_id for cue in manifest.cues] == ["cue-001", "cue-002"]
    assert [cue.duration_ms for cue in manifest.cues] == [100, 100]
    assert not (tmp_path / "tts" / "narration.wav").exists()


def test_cue_tts_manifest_order_must_match_plan(tmp_path: Path) -> None:
    manifest = synthesize_narration_cues(
        _v2_plan(), tmp_path / "tts", tmp_path / "cache",
        source_sha256="b" * 64, provider=CountingProvider(), converter=_converter,
    )
    reversed_manifest = CueTtsManifest(
        tuple(reversed(manifest.cues)), manifest.provider, manifest.voice_id,
        manifest.policy_version, manifest.cache_hits, manifest.cache_misses,
    )
    with pytest.raises(MvpError, match="cue IDs must exactly match"):
        validate_cue_tts_ids(_v2_plan(), reversed_manifest)
