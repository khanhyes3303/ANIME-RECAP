from __future__ import annotations

import json
from pathlib import Path

import pytest

from anime_review_mvp.editorial import load_locked_spans
from anime_review_mvp.errors import MvpError
from anime_review_mvp.models import Event, SourceRegionAnnotation, TruthDocument


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _truth(*, excluded: bool = False) -> TruthDocument:
    regions = (
        (
            SourceRegionAnnotation(
                "region-001",
                0,
                1_000,
                "OPENING",
                "EXCLUDE",
                "Opening sequence",
            ),
        )
        if excluded
        else ()
    )
    return TruthDocument(
        events=(Event("event-001", 1_000, 4_000, ("Jiro",), "Jiro runs.", "MAIN", 1.0),),
        source_regions=regions,
        source_region_scan_complete=True,
    )


def _payload() -> dict[str, object]:
    return {
        "spans": [
            {
                "span_id": "span-001",
                "text": "Jiro lao qua cổng như đang bị deadline dí.",
                "claim_ids": ["claim-001"],
                "event_ids": ["event-001"],
                "characters": ["Jiro"],
                "visible_action": "Jiro chạy qua cổng.",
                "source_ranges": [
                    {
                        "range_id": "range-001",
                        "source_start_ms": 1_000,
                        "source_end_ms": 4_000,
                        "scene_id": "scene-001",
                        "beat_id": "beat-001",
                        "shot_ids": ["shot-0001"],
                        "event_ids": ["event-001"],
                        "short_action_exception": False,
                    }
                ],
            }
        ],
        "claims": [
            {
                "claim_id": "claim-001",
                "kind": "ACTION",
                "text": "Jiro runs through the gate.",
                "evidence_event_ids": ["event-001"],
            }
        ],
        "owner": "CODEX",
    }


def test_locked_span_rejects_two_sentences(tmp_path: Path) -> None:
    payload = _payload()
    spans = payload["spans"]
    assert isinstance(spans, list)
    spans[0]["text"] = "Jiro lao qua cổng. Cậu tung cú đấm."

    with pytest.raises(MvpError, match="one sentence"):
        load_locked_spans(_write(tmp_path / "khoa_cau_canh.json", payload), _truth(), 10_000)


def test_locked_span_rejects_missing_visible_action(tmp_path: Path) -> None:
    payload = _payload()
    spans = payload["spans"]
    assert isinstance(spans, list)
    spans[0]["visible_action"] = ""

    with pytest.raises(MvpError, match="visible_action"):
        load_locked_spans(_write(tmp_path / "khoa_cau_canh.json", payload), _truth(), 10_000)


def test_locked_span_rejects_antigravity_ownership(tmp_path: Path) -> None:
    payload = _payload()
    payload["owner"] = "ANTIGRAVITY"

    with pytest.raises(MvpError, match="CODEX"):
        load_locked_spans(_write(tmp_path / "khoa_cau_canh.json", payload), _truth(), 10_000)


def test_locked_span_rejects_excluded_footage(tmp_path: Path) -> None:
    payload = _payload()
    spans = payload["spans"]
    assert isinstance(spans, list)
    ranges = spans[0]["source_ranges"]
    assert isinstance(ranges, list)
    ranges[0]["source_start_ms"] = 500

    with pytest.raises(MvpError, match="excluded source region"):
        load_locked_spans(
            _write(tmp_path / "khoa_cau_canh.json", payload),
            _truth(excluded=True),
            10_000,
        )


def test_locked_span_loads_strict_valid_contract(tmp_path: Path) -> None:
    document = load_locked_spans(
        _write(tmp_path / "khoa_cau_canh.json", _payload()),
        _truth(),
        10_000,
    )

    assert document.owner == "CODEX"
    assert document.spans[0].span_id == "span-001"
    assert document.spans[0].source_ranges[0].source_end_ms == 4_000
