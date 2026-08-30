from __future__ import annotations

import json
import os
import types
import uuid
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

from .errors import MvpError


def dump_json(path: Path, value: Any) -> None:
    if not is_dataclass(value):
        raise MvpError("JSON artifacts must be dataclass instances")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(value), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def atomic_dump_json(path: Path, value: Any) -> None:
    """Write one dataclass JSON artifact without exposing a partial file."""
    if not is_dataclass(value):
        raise MvpError("JSON artifacts must be dataclass instances")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(asdict(value), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError as exc:
        raise MvpError(f"cannot atomically write JSON artifact: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def atomic_append_jsonl(path: Path, value: Any) -> None:
    """Append a dataclass record by atomically replacing the JSONL ledger."""
    if not is_dataclass(value):
        raise MvpError("JSONL records must be dataclass instances")
    existing = b""
    if path.exists():
        try:
            existing = path.read_bytes()
        except OSError as exc:
            raise MvpError(f"cannot load JSONL ledger: {path}") from exc
        for line in existing.splitlines():
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                raise MvpError(f"cannot load JSONL ledger: {path}") from exc
    if existing and not existing.endswith(b"\n"):
        existing += b"\n"
    record = (json.dumps(asdict(value), ensure_ascii=False) + "\n").encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(existing + record)
        os.replace(temporary, path)
    except OSError as exc:
        raise MvpError(f"cannot atomically append JSONL ledger: {path}") from exc
    finally:
        temporary.unlink(missing_ok=True)


def load_json[T](path: Path, cls: type[T]) -> T:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MvpError(f"cannot load JSON artifact: {path}") from exc
    return _from_value(raw, cls)


def _from_value(value: Any, expected: Any) -> Any:
    origin = get_origin(expected)
    args = get_args(expected)
    if origin is tuple:
        if not isinstance(value, list):
            raise MvpError("JSON tuple field must be an array")
        item_type = args[0] if args else Any
        return tuple(_from_value(item, item_type) for item in value)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        for candidate in (item for item in args if item is not type(None)):
            try:
                return _from_value(value, candidate)
            except (MvpError, TypeError, ValueError):
                continue
        raise MvpError("JSON union field has no valid representation")
    if is_dataclass(expected):
        if not isinstance(value, dict):
            raise MvpError("JSON dataclass field must be an object")
        hints = get_type_hints(expected)
        allowed = {field.name for field in fields(expected)}
        if set(value) != allowed:
            raise MvpError("JSON object fields do not match the artifact contract")
        converted = {name: _from_value(value[name], hints[name]) for name in allowed}
        return expected(**converted)
    if expected is Any:
        return value
    if not isinstance(value, expected):
        raise MvpError(f"JSON value must be {expected.__name__}")
    return value
