"""Safe, bounded runtime storage for crawler-produced site data.

Crawler output is intentionally kept out of the source tree.  The store writes a
complete JSON document to a private temporary file and atomically replaces the
previous document while holding an advisory process lock.
"""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class RuntimeDataStore:
    def __init__(self, data_dir: Path, max_generated_updates: int) -> None:
        self.data_dir = data_dir
        self.max_generated_updates = max_generated_updates

    @property
    def updates_path(self) -> Path:
        return self.data_dir / "generated_updates.json"

    @property
    def hero_slides_path(self) -> Path:
        return self.data_dir / "generated_hero_slides.json"

    def initialize(self) -> None:
        self.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.data_dir.chmod(0o700)

    @contextmanager
    def _lock(self, name: str) -> Iterator[None]:
        self.initialize()
        lock_path = self.data_dir / f".{name}.lock"
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.chmod(lock_path, 0o600)
            with os.fdopen(descriptor, "r+") as lock_file:
                descriptor = -1
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            if descriptor != -1:
                os.close(descriptor)

    @staticmethod
    def _valid_items(payload: object) -> list[dict[str, Any]]:
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            return []
        return [item for item in payload["items"] if isinstance(item, dict)]

    def _read(self, path: Path) -> list[dict[str, Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return self._valid_items(payload)

    def _write(self, path: Path, items: list[dict[str, Any]]) -> None:
        self.initialize()
        payload = json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=self.data_dir)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary_file:
                temporary_file.write(payload)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, path)
            os.chmod(path, 0o600)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    @staticmethod
    def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in items:
            title = str(item.get("title", "")).strip()
            href = str(item.get("href", "")).strip()
            if not title or not href:
                continue
            key = (href, title.casefold())
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def read_updates(self) -> list[dict[str, Any]]:
        return self._read(self.updates_path)

    def write_updates(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self._lock("generated_updates"):
            bounded = self._dedupe(items)[: self.max_generated_updates]
            self._write(self.updates_path, bounded)
            return bounded

    def prepend_updates(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self._lock("generated_updates"):
            bounded = self._dedupe([*items, *self._read(self.updates_path)])[: self.max_generated_updates]
            self._write(self.updates_path, bounded)
            return bounded

    def read_hero_slides(self) -> list[dict[str, Any]]:
        return self._read(self.hero_slides_path)

    def write_hero_slides(self, slides: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self._lock("generated_hero_slides"):
            valid_slides = [slide for slide in slides if isinstance(slide, dict)]
            self._write(self.hero_slides_path, valid_slides)
            return valid_slides
