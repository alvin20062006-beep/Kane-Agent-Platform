from __future__ import annotations

import json
import os
import time
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_LOCKS: dict[str, threading.RLock] = {}


def _lock_for_path(path: str) -> threading.RLock:
    # One lock per canonical path for cross-repo concurrency (worker + API threads).
    if path not in _LOCKS:
        _LOCKS[path] = threading.RLock()
    return _LOCKS[path]


class FileStore(Generic[T]):
    """
    Minimal file-backed store (JSON array) for local persistence.

  Credentials and API profile keys may be stored in entity JSON when operators
  configure them via the API — see docs/BETA_LIMITATIONS.md (not KMS-backed).
    """

    def __init__(self, path: Path, model: type[T], id_field: str):
        self.path = path
        self.model = model
        self.id_field = id_field
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _lock_for_path(str(self.path))
        self._cache_signature: tuple[int, int] | None = None
        self._cache_raw: list[dict[str, Any]] | None = None

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

    def _read_raw_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            self._cache_signature = None
            self._cache_raw = []
            return []
        stat = self.path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        if self._cache_signature == signature and self._cache_raw is not None:
            return deepcopy(self._cache_raw)
        last_err: Exception | None = None
        text = ""
        for attempt in range(8):
            try:
                text = self.path.read_text(encoding="utf-8")
                last_err = None
                break
            except (PermissionError, OSError) as err:
                last_err = err
                time.sleep(0.05 * (attempt + 1))
        if last_err:
            raise last_err
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
        normalized = self._normalize_raw(data)
        self._cache_signature = signature
        self._cache_raw = deepcopy(normalized)
        return normalized

    def _read_raw(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_raw_unlocked()

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
            stat = self.path.stat()
            self._cache_signature = (stat.st_mtime_ns, stat.st_size)
            self._cache_raw = deepcopy(items)

    def list(self) -> list[T]:
        return [self.model.model_validate(x) for x in self._read_raw()]

    def get(self, item_id: str) -> T | None:
        for x in self._read_raw():
            if str(x.get(self.id_field)) == item_id:
                return self.model.model_validate(x)
        return None

    def upsert(self, item: T) -> T:
        with self._lock:
            raw = self._read_raw_unlocked()
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

    def create_if_absent(self, item: T) -> bool:
        item_id = str(getattr(item, self.id_field))
        with self._lock:
            raw = self._read_raw_unlocked()
            for existing in raw:
                if str(existing.get(self.id_field)) == item_id:
                    return False
            raw.append(item.model_dump())
            self._write_raw(raw)
            return True

    def compare_and_swap(self, item: T, expected: dict[str, Any]) -> bool:
        item_id = str(getattr(item, self.id_field))
        with self._lock:
            raw = self._read_raw_unlocked()
            out: list[dict[str, Any]] = []
            swapped = False
            for existing in raw:
                if str(existing.get(self.id_field)) != item_id:
                    out.append(existing)
                    continue
                if all(existing.get(field) == value for field, value in expected.items()):
                    out.append(item.model_dump())
                    swapped = True
                else:
                    out.append(existing)
            if swapped:
                self._write_raw(out)
            return swapped

    def delete(self, item_id: str) -> bool:
        """Remove an item by id. Returns True if the item was found and deleted."""
        with self._lock:
            raw = self._read_raw_unlocked()
            out = [x for x in raw if str(x.get(self.id_field)) != item_id]
            if len(out) == len(raw):
                return False
            self._write_raw(out)
            return True

