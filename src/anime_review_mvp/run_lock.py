from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import MvpError


@contextmanager
def exclusive_run_lock(run_dir: Path, purpose: str) -> Iterator[None]:
    """Prevent overlapping processes from mutating the same run."""
    run_dir.mkdir(parents=True, exist_ok=True)
    lock_path = run_dir / f".{purpose}.lock"
    lock_file = lock_path.open("a+b")
    acquired = False
    try:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise MvpError(f"{purpose} is already running for this run") from exc
        acquired = True
        yield
    finally:
        if acquired:
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()
