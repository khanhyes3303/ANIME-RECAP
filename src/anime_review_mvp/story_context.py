from __future__ import annotations

from .errors import MvpError
from .situations import CharacterContext, NarrationPlan, StoryContext, TermContext


def validate_newcomer_context(
    plan: NarrationPlan, initial_context: StoryContext
) -> StoryContext:
    """Walk narration in playback order and reject unexplained names and terms."""
    characters = {item.name: item for item in initial_context.characters}
    terms = {item.term: item for item in initial_context.terms}
    for unit in plan.units:
        for cue in unit.cues:
            for name in cue.introduces_characters:
                characters.setdefault(
                    name,
                    CharacterContext(name, "introduced by narration", cue.cue_id),
                )
            for term in cue.introduces_terms:
                terms.setdefault(
                    term,
                    TermContext(term, "explained by narration", cue.cue_id),
                )
            for name in cue.mentions_characters:
                if name not in characters:
                    raise MvpError(f"CHARACTER_USED_BEFORE_INTRODUCTION: {name}")
            for term in cue.mentions_terms:
                if term not in terms:
                    raise MvpError(f"TERM_USED_BEFORE_EXPLANATION: {term}")
    last_outcome = initial_context.last_outcome
    if plan.units and plan.units[-1].factual_claims:
        last_outcome = plan.units[-1].factual_claims[-1]
    return StoryContext(
        tuple(characters.values()),
        tuple(terms.values()),
        initial_context.unresolved_threads,
        last_outcome,
    )
