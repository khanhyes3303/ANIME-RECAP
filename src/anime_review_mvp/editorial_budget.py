from __future__ import annotations

from dataclasses import dataclass

from .errors import MvpError
from .situations import CueTtsManifest, EditorialPolicy


@dataclass(frozen=True, slots=True)
class EpisodeVoiceBudget:
    total_voice_duration_ms: int
    minimum_program_duration_ms: int
    maximum_program_duration_ms: int


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
