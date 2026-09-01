from __future__ import annotations

import pytest

from anime_review_mvp.editorial_budget import (
    validate_episode_voice_budget,
    validate_episode_word_budget,
)
from anime_review_mvp.errors import MvpError
from anime_review_mvp.situations import (
    CueTts,
    CueTtsManifest,
    EditorialPolicy,
    EvidenceRange,
    NarrationPlan,
    NarrationUnit,
)


def _manifest(*durations_ms: int) -> CueTtsManifest:
    cues = tuple(
        CueTts(
            f"cue-{index:03d}",
            f"unit-{index:03d}",
            f"{index}.wav",
            f"{index}.mp3",
            duration_ms,
            f"{index:064x}",
        )
        for index, duration_ms in enumerate(durations_ms, start=1)
    )
    return CueTtsManifest(cues, "fake", "voice", "situation-v2", 0, len(cues))


def test_voice_budget_rejects_episode_that_cannot_reach_seven_minutes() -> None:
    with pytest.raises(MvpError, match="EPISODE_VOICE_BUDGET_TOO_SHORT"):
        validate_episode_voice_budget(_manifest(138_000, 139_000), EditorialPolicy())


def test_voice_budget_rejects_episode_that_must_exceed_twelve_minutes() -> None:
    with pytest.raises(MvpError, match="EPISODE_VOICE_BUDGET_TOO_LONG"):
        validate_episode_voice_budget(_manifest(360_000, 361_000), EditorialPolicy())


def test_voice_budget_accepts_continuous_episode_inside_production_window() -> None:
    budget = validate_episode_voice_budget(_manifest(210_000, 211_000), EditorialPolicy())

    assert budget.minimum_program_duration_ms == 421_080
    assert budget.maximum_program_duration_ms == 421_600
    assert budget.total_voice_duration_ms == 421_000


def _word_plan(words: int) -> NarrationPlan:
    text = " ".join(f"từ{i}" for i in range(words))
    evidence = EvidenceRange(
        "range-001",
        "situation-001",
        1_000,
        2_000,
        ("shot-001",),
        ("event-001",),
        (),
        ("frame-001.jpg",),
        "Sự kiện",
    )
    unit = NarrationUnit(
        "unit-001",
        "situation-001",
        ("Sự kiện",),
        text,
        "",
        "",
        (evidence,),
        "DRAFT",
    )
    return NarrationPlan("LOCAL_EDITOR", "situation-v1", (unit,))


@pytest.mark.parametrize(
    ("words", "error"),
    ((1_049, "TOO_SHORT"), (1_801, "TOO_LONG")),
)
def test_word_budget_rejects_implausible_seven_to_twelve_minute_script(
    words: int, error: str
) -> None:
    with pytest.raises(MvpError, match=f"EPISODE_SCRIPT_BUDGET_{error}"):
        validate_episode_word_budget(_word_plan(words))


def test_word_budget_accepts_script_at_seven_minute_floor() -> None:
    budget = validate_episode_word_budget(_word_plan(1_050))

    assert budget.total_words == 1_050
    assert budget.minimum_words == 1_050
    assert budget.maximum_words == 1_800
