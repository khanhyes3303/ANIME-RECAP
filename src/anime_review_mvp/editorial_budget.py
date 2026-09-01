from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import MvpError
from .situations import CueTtsManifest, EditorialPolicy, NarrationPlan

_WORD_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class EpisodeVoiceBudget:
    total_voice_duration_ms: int
    minimum_program_duration_ms: int
    maximum_program_duration_ms: int


@dataclass(frozen=True, slots=True)
class EpisodeWordBudget:
    total_words: int
    minimum_words: int = 1_050
    maximum_words: int = 1_800


def validate_episode_word_budget(plan: NarrationPlan) -> EpisodeWordBudget:
    texts = tuple(
        cue.text
        for unit in plan.units
        for cue in unit.cues
    ) or tuple(unit.narration_text for unit in plan.units)
    budget = EpisodeWordBudget(
        total_words=sum(len(_WORD_TOKEN.findall(text)) for text in texts)
    )
    if budget.total_words < budget.minimum_words:
        raise MvpError(
            "EPISODE_SCRIPT_BUDGET_TOO_SHORT: expand the complete episode before TTS"
        )
    if budget.total_words > budget.maximum_words:
        raise MvpError(
            "EPISODE_SCRIPT_BUDGET_TOO_LONG: shorten the complete episode before TTS"
        )
    return budget


def validate_episode_voice_budget(
    tts: CueTtsManifest,
    policy: EditorialPolicy,
    *,
    minimum_inter_cue_pause_ms: int = 80,
    maximum_inter_cue_pause_ms: int = 600,
) -> EpisodeVoiceBudget:
    """Reject narration that cannot fit the production duration window.

    This is deliberately a feasibility gate, not an editor: it never pads,
    stretches, rewrites, or selects footage on Antigravity's behalf.
    """
    if not 0 <= minimum_inter_cue_pause_ms <= maximum_inter_cue_pause_ms:
        raise MvpError("episode voice pause policy is invalid")
    voice_ms = sum(cue.duration_ms for cue in tts.cues)
    gaps = max(0, len(tts.cues) - 1)
    minimum_ms = voice_ms + gaps * minimum_inter_cue_pause_ms
    maximum_ms = voice_ms + gaps * maximum_inter_cue_pause_ms
    if maximum_ms < policy.target_minimum_ms:
        raise MvpError(
            "EPISODE_VOICE_BUDGET_TOO_SHORT: Antigravity must rewrite and "
            "expand plot narration before timeline construction"
        )
    if minimum_ms > policy.target_maximum_ms:
        raise MvpError(
            "EPISODE_VOICE_BUDGET_TOO_LONG: Antigravity must shorten narration "
            "before timeline construction"
        )
    return EpisodeVoiceBudget(voice_ms, minimum_ms, maximum_ms)
