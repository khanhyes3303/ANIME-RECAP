from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from anime_review_mvp.jsonio import atomic_append_jsonl, atomic_dump_json


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
