from __future__ import annotations

import hashlib
import json
import os
import types
import uuid
from dataclasses import asdict, dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

from .errors import MvpError


@dataclass(frozen=True, slots=True)
class JsonPairManifest:
    task_id: str
    first_sha256: str
    second_sha256: str


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_publish_json_pair(
    first_path: Path,
    first_value: Any,
    second_path: Path,
    second_value: Any,
    manifest_path: Path,
    *,
    task_id: str,
) -> JsonPairManifest:
    """Publish two JSON artifacts and make the pair canonical via a final manifest."""
    if not task_id.strip() or not is_dataclass(first_value) or not is_dataclass(second_value):
        raise MvpError("JSON pair publication is invalid")
    first_path.parent.mkdir(parents=True, exist_ok=True)
    second_path.parent.mkdir(parents=True, exist_ok=True)
    first_temp = first_path.with_name(f".{first_path.name}.{uuid.uuid4().hex}.tmp")
    second_temp = second_path.with_name(f".{second_path.name}.{uuid.uuid4().hex}.tmp")
    manifest_path.unlink(missing_ok=True)
    try:
        first_temp.write_text(
            json.dumps(asdict(first_value), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        second_temp.write_text(
            json.dumps(asdict(second_value), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest = JsonPairManifest(task_id, _sha256(first_temp), _sha256(second_temp))
        os.replace(first_temp, first_path)
        os.replace(second_temp, second_path)
        atomic_dump_json(manifest_path, manifest)
        return manifest
    except OSError as exc:
        raise MvpError("cannot atomically publish JSON pair") from exc
    finally:
        first_temp.unlink(missing_ok=True)
        second_temp.unlink(missing_ok=True)


def require_json_pair_manifest(
    first_path: Path,
    second_path: Path,
    manifest_path: Path,
) -> JsonPairManifest:
    manifest = load_json(manifest_path, JsonPairManifest)
    try:
        matches = (
            _sha256(first_path) == manifest.first_sha256
            and _sha256(second_path) == manifest.second_sha256
        )
    except OSError as exc:
        raise MvpError("accepted JSON pair is incomplete") from exc
    if not matches:
        raise MvpError("accepted JSON pair hash mismatch")
    return manifest


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
        contract_fields = {field.name: field for field in fields(expected)}
        if not set(value) <= set(contract_fields):
            raise MvpError("JSON object fields do not match the artifact contract")
        required = {
            name
            for name, field in contract_fields.items()
            if not field.metadata.get("json_optional", False)
        }
        if not required <= set(value):
            raise MvpError("JSON object fields do not match the artifact contract")
        converted = {name: _from_value(raw, hints[name]) for name, raw in value.items()}
        return expected(**converted)
    if expected is Any:
        return value
    if not isinstance(value, expected):
        raise MvpError(f"JSON value must be {expected.__name__}")
    return value
