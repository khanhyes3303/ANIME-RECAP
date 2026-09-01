from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from anime_review_mvp.errors import MvpError
from anime_review_mvp.run_identity import (
    RunCodeIdentity,
    capture_run_code_identity,
    validate_run_code_identity,
)


def test_identity_rejects_engine_from_another_checkout(tmp_path: Path) -> None:
    recorded = RunCodeIdentity(
        str((tmp_path / "repo-a").resolve()),
        "a" * 40,
        "anime-review-v3",
    )

    with pytest.raises(MvpError, match="RUN_CODE_IDENTITY_MISMATCH"):
        validate_run_code_identity(
            tmp_path / "repo-a" / "Tam_dang_xu_ly" / "run-1",
            recorded,
            engine_root=tmp_path / "repo-b",
        )


def test_identity_rejects_engine_older_than_run_commit(tmp_path: Path) -> None:
    recorded = RunCodeIdentity(str(tmp_path.resolve()), "a" * 40, "anime-review-v3")

    def not_descendant(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="", stderr="not an ancestor")

    with pytest.raises(MvpError, match="RUN_CODE_IDENTITY_MISMATCH"):
        validate_run_code_identity(
            tmp_path / "run",
            recorded,
            engine_root=tmp_path,
            runner=not_descendant,
        )


def test_identity_accepts_newer_engine_in_same_checkout(tmp_path: Path) -> None:
    recorded = RunCodeIdentity(str(tmp_path.resolve()), "a" * 40, "anime-review-v3")

    def descendant(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    validate_run_code_identity(
        tmp_path / "run",
        recorded,
        engine_root=tmp_path,
        runner=descendant,
    )


def test_identity_rejects_policy_changed_after_run_started(tmp_path: Path) -> None:
    recorded = RunCodeIdentity(
        str(tmp_path.resolve()),
        "a" * 40,
        "anime-review-v3",
        "b" * 64,
    )

    def descendant(*args: object, **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with pytest.raises(MvpError, match="RUN_POLICY_IDENTITY_MISMATCH"):
        validate_run_code_identity(
            tmp_path / "run",
            recorded,
            engine_root=tmp_path,
            runner=descendant,
            policy_hasher=lambda _root: "c" * 64,
        )


def test_capture_identity_uses_repository_containing_run(tmp_path: Path) -> None:
    repository = (tmp_path / "repo").resolve()
    responses = iter(
        (
            SimpleNamespace(returncode=0, stdout=str(repository) + "\n", stderr=""),
            SimpleNamespace(returncode=0, stdout="c" * 40 + "\n", stderr=""),
        )
    )

    identity = capture_run_code_identity(
        repository / "Tam_dang_xu_ly" / "run",
        runner=lambda *args, **kwargs: next(responses),
    )

    assert identity.repository_root == str(repository)
    assert identity.git_commit == "c" * 40
    assert identity.contract_version == "anime-review-v3"
    assert len(identity.policy_sha256) == 64
