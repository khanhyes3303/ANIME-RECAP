from __future__ import annotations

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.situations import (
    EvidenceRange,
    NarrationClaim,
    NarrationCue,
    NarrationPlan,
    NarrationUnit,
    SemanticShotUse,
    StoryContext,
)
from anime_review_mvp.story_context import validate_newcomer_context


def _plan(cue: NarrationCue) -> NarrationPlan:
    use = SemanticShotUse("shot-001", "event-001", "SETUP", "Giới thiệu sự việc.")
    evidence = EvidenceRange(
        "range-001", "situation-001", 1_000, 5_000, ("shot-001",),
        ("event-001",), ("transcript-001",), ("frame-001",), "Giới thiệu sự việc.",
        "event-001", "SETUP", "Giới thiệu sự việc.", (use,),
    )
    unit = NarrationUnit(
        "unit-001", "situation-001", ("Sự việc bắt đầu.",), cue.text, "", "",
        (evidence,), "LOCKED", (cue,),
    )
    return NarrationPlan(
        "LOCAL_EDITOR", "situation-v2", (unit,),
        (NarrationClaim("claim-001", "Sự việc bắt đầu.", ("event-001",)),),
    )


def _cue(**changes: object) -> NarrationCue:
    values = {
        "cue_id": "cue-001", "situation_id": "situation-001",
        "text": "Rago xuất hiện.", "claim_ids": ("claim-001",),
        "visual_anchor_source_ms": 1_000, "anchor_kind": "SETUP",
        "transcript_refs": ("transcript-001",), "frame_refs": ("frame-001",),
        "shot_ids": ("shot-001",), "introduces_characters": (),
        "mentions_characters": (), "introduces_terms": (), "mentions_terms": (),
    }
    values.update(changes)
    return NarrationCue(**values)


def _empty() -> StoryContext:
    return StoryContext((), (), (), "")


def test_character_cannot_be_used_before_introduction() -> None:
    with pytest.raises(MvpError, match="CHARACTER_USED_BEFORE_INTRODUCTION.*Rago"):
        validate_newcomer_context(_plan(_cue(mentions_characters=("Rago",))), _empty())


def test_character_can_be_introduced_and_used_in_same_cue() -> None:
    context = validate_newcomer_context(
        _plan(_cue(introduces_characters=("Rago",), mentions_characters=("Rago",))),
        _empty(),
    )
    assert context.characters[0].name == "Rago"


def test_term_cannot_be_used_before_plain_explanation() -> None:
    with pytest.raises(MvpError, match="TERM_USED_BEFORE_EXPLANATION.*Hắc Tinh"):
        validate_newcomer_context(_plan(_cue(mentions_terms=("Hắc Tinh",))), _empty())
