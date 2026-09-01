from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from anime_review_mvp.jsonio import (
    atomic_append_jsonl,
    atomic_dump_json,
    atomic_publish_json_pair,
    require_json_pair_manifest,
)


@dataclass(frozen=True)
class Revision:
    revision: int


def test_atomic_dump_json_replaces_complete_document_without_temporary_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "artifact.json"

    atomic_dump_json(path, Revision(1))
    atomic_dump_json(path, Revision(2))

    assert json.loads(path.read_text(encoding="utf-8")) == {"revision": 2}
    assert not tuple(tmp_path.glob("*.tmp"))


def test_atomic_append_jsonl_preserves_order_and_writes_valid_records(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"

    atomic_append_jsonl(path, Revision(1))
    atomic_append_jsonl(path, Revision(2))

    assert [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] == [
        {"revision": 1},
        {"revision": 2},
    ]
    assert not tuple(tmp_path.glob("*.tmp"))


def test_json_pair_is_canonical_only_after_both_hashes_are_committed(tmp_path: Path) -> None:
    first = tmp_path / "situations.json"
    second = tmp_path / "narration_plan.json"
    manifest = tmp_path / "episode_review_acceptance.json"

    atomic_publish_json_pair(
        first,
        Revision(1),
        second,
        Revision(2),
        manifest,
        task_id="episode-review-001",
    )

    accepted = require_json_pair_manifest(first, second, manifest)
    assert accepted.task_id == "episode-review-001"
    assert accepted.first_sha256 != accepted.second_sha256
