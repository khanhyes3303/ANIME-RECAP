from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .errors import MvpError


class Completed(Protocol):
    returncode: int
    stdout: str


class Runner(Protocol):
    def __call__(self, *args: object, **kwargs: object) -> Completed: ...


@dataclass(frozen=True, slots=True)
class RunCodeIdentity:
    repository_root: str
    git_commit: str
    contract_version: str = "anime-review-v3"
    policy_sha256: str = ""


def _calculate_policy_sha256(root: Path) -> str:
    from .antigravity import calculate_policy_sha256

    return calculate_policy_sha256(root)


def _git_output(path: Path, arguments: list[str], runner: Runner) -> str:
    completed = runner(
        ["git", "-C", str(path), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or not value:
        raise MvpError("RUN_CODE_IDENTITY_UNAVAILABLE")
    return value


def capture_run_code_identity(
    path: Path,
    *,
    runner: Runner = subprocess.run,
) -> RunCodeIdentity:
    repository_root = Path(
        _git_output(path.resolve(), ["rev-parse", "--show-toplevel"], runner)
    ).resolve()
    git_commit = _git_output(repository_root, ["rev-parse", "HEAD"], runner)
    return RunCodeIdentity(
        str(repository_root),
        git_commit,
        policy_sha256=_calculate_policy_sha256(repository_root),
    )


def validate_run_code_identity(
    run_dir: Path,
    recorded: RunCodeIdentity,
    *,
    engine_root: Path | None = None,
    runner: Runner = subprocess.run,
    policy_hasher: Callable[[Path], str] = _calculate_policy_sha256,
) -> None:
    del run_dir
    actual_root = (engine_root or Path(__file__).resolve().parents[2]).resolve()
    expected_root = Path(recorded.repository_root).resolve()
    if actual_root != expected_root or recorded.contract_version != "anime-review-v3":
        raise MvpError("RUN_CODE_IDENTITY_MISMATCH")
    completed = runner(
        [
            "git",
            "-C",
            str(actual_root),
            "merge-base",
            "--is-ancestor",
            recorded.git_commit,
            "HEAD",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise MvpError("RUN_CODE_IDENTITY_MISMATCH")
    if recorded.policy_sha256 and policy_hasher(actual_root) != recorded.policy_sha256:
        raise MvpError("RUN_POLICY_IDENTITY_MISMATCH")
