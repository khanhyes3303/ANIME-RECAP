from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import MvpError


@dataclass(frozen=True, slots=True)
class BrowserTurn:
    index: int
    prompt_sha256: str
    response_sha256: str
    conversation_url: str
    started_at: str
    finished_at: str


@dataclass(frozen=True, slots=True)
class GeminiSessionMetadata:
    run_id: str
    chrome_pid: int
    debugger_address: str
    conversation_url: str | None
    started_at: str
    phase_turns: dict[str, int]

    @classmethod
    def from_dict(cls, payload: object) -> GeminiSessionMetadata:
        if not isinstance(payload, dict):
            raise MvpError("Gemini session metadata is malformed")
        try:
            run_id = str(payload["run_id"])
            chrome_pid = int(payload["chrome_pid"])
            debugger_address = str(payload["debugger_address"])
            conversation_url_value = payload.get("conversation_url")
            conversation_url = (
                None if conversation_url_value is None else str(conversation_url_value)
            )
            started_at = str(payload["started_at"])
            raw_turns = payload.get("phase_turns", {})
            if not isinstance(raw_turns, dict):
                raise TypeError("phase_turns")
            phase_turns = {str(key): int(value) for key, value in raw_turns.items()}
        except (KeyError, TypeError, ValueError) as exc:
            raise MvpError("Gemini session metadata is malformed") from exc
        if not run_id or chrome_pid <= 0 or not debugger_address or not started_at:
            raise MvpError("Gemini session metadata is malformed")
        if any(value < 0 for value in phase_turns.values()):
            raise MvpError("Gemini session turn count is invalid")
        return cls(run_id, chrome_pid, debugger_address, conversation_url, started_at, phase_turns)


class GeminiSessionRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> GeminiSessionMetadata | None:
        if not self.path.is_file():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MvpError("Gemini session metadata is unreadable") from exc
        return GeminiSessionMetadata.from_dict(payload)

    def save(self, metadata: GeminiSessionMetadata) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(asdict(metadata), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def assert_attachable(
        self,
        run_id: str,
        *,
        probe: Callable[[str], bool] | None = None,
        pid_alive: Callable[[int], bool] | None = None,
    ) -> GeminiSessionMetadata:
        metadata = self.load()
        if metadata is None:
            raise MvpError("Gemini session is not attachable: metadata is missing")
        if metadata.run_id != run_id:
            raise MvpError("Gemini session belongs to another run")
        check_pid = pid_alive or _pid_is_alive
        check_probe = probe or _debugger_is_alive
        if not check_pid(metadata.chrome_pid) or not check_probe(metadata.debugger_address):
            raise MvpError("Gemini session is not attachable: Chrome is stale")
        return metadata

    def increment_turn(self, run_id: str, phase: str, *, max_turns: int = 6) -> int:
        if max_turns <= 0:
            raise MvpError("Gemini session turn limit is invalid")
        metadata = self.load()
        if metadata is None:
            raise MvpError("Gemini session is not attachable: metadata is missing")
        if metadata.run_id != run_id:
            raise MvpError("Gemini session belongs to another run")
        phase_key = phase.upper()
        current = metadata.phase_turns.get(phase_key, 0)
        if current >= max_turns:
            raise MvpError("Gemini conversation turn limit reached")
        updated_turns = dict(metadata.phase_turns)
        updated_turns[phase_key] = current + 1
        self.save(
            GeminiSessionMetadata(
                metadata.run_id,
                metadata.chrome_pid,
                metadata.debugger_address,
                metadata.conversation_url,
                metadata.started_at,
                updated_turns,
            )
        )
        return current + 1

    def update_conversation(self, run_id: str, conversation_url: str) -> GeminiSessionMetadata:
        metadata = self.load()
        if metadata is None:
            raise MvpError("Gemini session is not attachable: metadata is missing")
        if metadata.run_id != run_id:
            raise MvpError("Gemini session belongs to another run")
        updated = GeminiSessionMetadata(
            metadata.run_id,
            metadata.chrome_pid,
            metadata.debugger_address,
            conversation_url,
            metadata.started_at,
            dict(metadata.phase_turns),
        )
        self.save(updated)
        return updated

    def clear(self, run_id: str) -> None:
        metadata = self.load()
        if metadata is None:
            return
        if metadata.run_id != run_id:
            raise MvpError("Gemini session belongs to another run")
        try:
            self.path.unlink()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise MvpError("Gemini session metadata could not be removed") from exc


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _windows_pid_is_alive(pid)
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _windows_pid_is_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, wintypes.LPDWORD)
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _debugger_is_alive(address: str) -> bool:
    try:
        with urllib.request.urlopen(f"http://{address}/json/version", timeout=1):
            return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
