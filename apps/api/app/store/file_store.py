from __future__ import annotations

import json
import os
import time
import threading
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_LOCKS: dict[str, threading.Lock] = {}


def _lock_for_path(path: str) -> threading.Lock:
    # One lock per canonical path for cross-repo concurrency (worker + API threads).
    if path not in _LOCKS:
        _LOCKS[path] = threading.Lock()
    return _LOCKS[path]


class FileStore(Generic[T]):
    """
    Minimal file-backed store (JSON array) for Phase 2.

    - No DB required
    - No secrets persisted in this phase
    - Safe placeholder for later DB-backed repositories
    """

    def __init__(self, path: Path, model: type[T], id_field: str):
        self.path = path
        self.model = model
        self.id_field = id_field
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _lock_for_path(str(self.path))

    def _normalize_raw(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        index_by_id: dict[str, int] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get(self.id_field)
            if item_id is None:
                deduped.append(item)
                continue
            key = str(item_id)
            if key in index_by_id:
                deduped[index_by_id[key]] = item
            else:
                index_by_id[key] = len(deduped)
                deduped.append(item)
        return deduped

    def _read_raw(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        text = self.path.read_text(encoding="utf-8")
        if not text.strip():
            return []
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder()
            parsed, _end = decoder.raw_decode(text)
            if not isinstance(parsed, list):
                raise ValueError("Store data must start with a JSON array.")
            data = parsed
            self._write_raw(self._normalize_raw(data))
        if not isinstance(data, list):
            raise ValueError("Store data must be a JSON array.")
        return self._normalize_raw(data)

    def _write_raw(self, items: list[dict[str, Any]]) -> None:
        with self._lock:
            tmp = self.path.with_name(
                f"{self.path.name}.{os.getpid()}.{time.time_ns()}.tmp"
            )
            tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
            # Windows can intermittently fail atomic replace due to AV/indexing or concurrent readers.
            # Retry briefly to make file-backed persistence robust under worker+API concurrency.
            last_err: Exception | None = None
            for attempt in range(8):
                try:
                    os.replace(tmp, self.path)
                    last_err = None
                    break
                except (PermissionError, OSError) as err:
                    last_err = err
                    time.sleep(0.05 * (attempt + 1))
            if last_err:
                raise last_err

    def list(self) -> list[T]:
        return [self.model.model_validate(x) for x in self._read_raw()]

    def get(self, item_id: str) -> T | None:
        for x in self._read_raw():
            if str(x.get(self.id_field)) == item_id:
                return self.model.model_validate(x)
        return None

    def upsert(self, item: T) -> T:
        raw = self._read_raw()
        item_id = getattr(item, self.id_field)
        out: list[dict[str, Any]] = []
        replaced = False
        for x in raw:
            if str(x.get(self.id_field)) == str(item_id):
                out.append(item.model_dump())
                replaced = True
            else:
                out.append(x)
        if not replaced:
            out.append(item.model_dump())
        self._write_raw(out)
        return item

    def delete(self, item_id: str) -> bool:
        """Remove an item by id. Returns True if the item was found and deleted."""
        raw = self._read_raw()
        out = [x for x in raw if str(x.get(self.id_field)) != item_id]
        if len(out) == len(raw):
            return False
        self._write_raw(out)
        return True

