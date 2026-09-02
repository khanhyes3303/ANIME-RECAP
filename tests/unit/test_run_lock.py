from __future__ import annotations

from pathlib import Path

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.run_lock import exclusive_run_lock


def test_exclusive_run_lock_rejects_a_second_operator_for_the_same_run(
    tmp_path: Path,
) -> None:
    with (
        exclusive_run_lock(tmp_path, "operator"),
        pytest.raises(MvpError, match="operator is already running"),
        exclusive_run_lock(tmp_path, "operator"),
    ):
        pass


def test_exclusive_run_lock_is_released_when_the_operator_finishes(
    tmp_path: Path,
) -> None:
    with exclusive_run_lock(tmp_path, "operator"):
        pass

    with exclusive_run_lock(tmp_path, "operator"):
        pass
