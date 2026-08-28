from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.jsonio import dump_json, load_json
from anime_review_mvp.models import Claim, Event, NarrationCue, ScriptDocument


def test_event_rejects_an_interval_that_runs_backwards() -> None:
    with pytest.raises(MvpError, match="event interval"):
        Event("E001", 2_000, 1_000, ("A",), "sai", "CORE", 1.0)


def test_claim_rejects_missing_factual_evidence() -> None:
    with pytest.raises(MvpError, match="factual evidence"):
        Claim("C001", "ACTION", "A chạy", ())


def test_script_round_trip_preserves_vietnamese_text_and_tuples(tmp_path: Path) -> None:
    script = ScriptDocument(
        (
            NarrationCue(
                "N001",
                "Cậu này chạy như bị dí KPI.",
                ("C001",),
                ("E001",),
                True,
            ),
        )
    )
    path = tmp_path / "script.json"

    dump_json(path, script)

    assert load_json(path, ScriptDocument) == script
    assert "dí KPI" in path.read_text(encoding="utf-8")
