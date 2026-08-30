from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from anime_review_mvp import gemini_session
from anime_review_mvp.errors import MvpError
from anime_review_mvp.gemini_session import (
    GeminiSessionMetadata,
    GeminiSessionRegistry,
    _pid_is_alive,
)


def _metadata(run_id: str = "run-1") -> GeminiSessionMetadata:
    return GeminiSessionMetadata(
        run_id=run_id,
        chrome_pid=1234,
        debugger_address="127.0.0.1:9222",
        conversation_url=None,
        started_at="2026-08-30T12:00:00+00:00",
        phase_turns={"SCRIPT": 0},
    )


def test_session_registry_round_trips_metadata(tmp_path) -> None:
    registry = GeminiSessionRegistry(tmp_path / "session.json")
    registry.save(_metadata())

    assert registry.load() == _metadata()
    assert json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))["run_id"] == "run-1"


def test_session_registry_rejects_another_run(tmp_path) -> None:
    registry = GeminiSessionRegistry(tmp_path / "session.json")
    registry.save(_metadata())

    with pytest.raises(MvpError, match="another run"):
        registry.assert_attachable("run-2", probe=lambda _: True, pid_alive=lambda _: True)


def test_session_registry_rejects_stale_pid_or_debugger(tmp_path) -> None:
    registry = GeminiSessionRegistry(tmp_path / "session.json")
    registry.save(_metadata())

    with pytest.raises(MvpError, match="not attachable"):
        registry.assert_attachable("run-1", probe=lambda _: False, pid_alive=lambda _: True)

    with pytest.raises(MvpError, match="not attachable"):
        registry.assert_attachable("run-1", probe=lambda _: True, pid_alive=lambda _: False)


def test_session_registry_limits_each_phase_to_six_turns(tmp_path) -> None:
    registry = GeminiSessionRegistry(tmp_path / "session.json")
    registry.save(_metadata())

    for expected in range(1, 7):
        assert registry.increment_turn("run-1", "SCRIPT", max_turns=6) == expected

    with pytest.raises(MvpError, match="turn limit"):
        registry.increment_turn("run-1", "SCRIPT", max_turns=6)


def test_session_registry_preflights_turn_without_consuming_it(tmp_path) -> None:
    registry = GeminiSessionRegistry(tmp_path / "session.json")
    registry.save(_metadata())

    assert registry.next_turn("run-1", "SCRIPT", max_turns=6) == 1
    assert registry.load() == _metadata()

    for _ in range(6):
        registry.increment_turn("run-1", "SCRIPT", max_turns=6)

    with pytest.raises(MvpError, match="turn limit"):
        registry.next_turn("run-1", "SCRIPT", max_turns=6)


def test_session_registry_starts_a_new_chat_without_closing_chrome(tmp_path) -> None:
    registry = GeminiSessionRegistry(tmp_path / "session.json")
    registry.save(
        GeminiSessionMetadata(
            "run-1",
            1234,
            "127.0.0.1:9222",
            "https://gemini.google.com/app/old-chat",
            "2026-08-30T12:00:00+00:00",
            {"SCRIPT": 5, "PROXY": 3},
        )
    )

    updated = registry.start_new_chat(
        "run-1", started_at="2026-08-30T13:00:00+00:00"
    )

    assert updated.chrome_pid == 1234
    assert updated.debugger_address == "127.0.0.1:9222"
    assert updated.conversation_url is None
    assert updated.phase_turns == {}
    assert updated.started_at == "2026-08-30T13:00:00+00:00"


def test_session_registry_clear_is_run_scoped(tmp_path) -> None:
    path = tmp_path / "session.json"
    registry = GeminiSessionRegistry(path)
    registry.save(_metadata())

    with pytest.raises(MvpError, match="another run"):
        registry.clear("run-2")
    assert path.is_file()

    registry.clear("run-1")
    assert not path.exists()


def test_pid_probe_uses_windows_process_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def posix_probe(_pid: int, _signal: int) -> None:
        raise OSError("WinError 87")

    monkeypatch.setattr(gemini_session, "sys", SimpleNamespace(platform="win32"), raising=False)
    monkeypatch.setattr(gemini_session.os, "kill", posix_probe)
    monkeypatch.setattr(
        gemini_session,
        "_windows_pid_is_alive",
        lambda pid: pid == 1234,
        raising=False,
    )

    assert _pid_is_alive(1234) is True
