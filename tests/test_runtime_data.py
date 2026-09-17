from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from app.runtime_data import RuntimeDataStore


class RuntimeDataStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary_directory.name) / "data"
        self.store = RuntimeDataStore(self.data_dir, max_generated_updates=2)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_updates_are_atomically_persisted_and_capped(self) -> None:
        self.store.write_updates(
            [
                {"title": "最新", "href": "https://example.com/latest"},
                {"title": "第二", "href": "https://example.com/second"},
                {"title": "第三", "href": "https://example.com/third"},
            ]
        )

        updates_path = self.data_dir / "generated_updates.json"
        self.assertEqual(self.store.read_updates(), [
            {"title": "最新", "href": "https://example.com/latest"},
            {"title": "第二", "href": "https://example.com/second"},
        ])
        self.assertEqual(json.loads(updates_path.read_text(encoding="utf-8"))["items"][0]["title"], "最新")
        self.assertEqual(updates_path.stat().st_mode & 0o077, 0)
        self.assertFalse(updates_path.with_suffix(".json.tmp").exists())

    def test_updates_dedupe_existing_values_without_importing_python_modules(self) -> None:
        self.store.write_updates([{"title": "既有", "href": "https://example.com/a"}])
        merged = self.store.prepend_updates(
            [
                {"title": "新內容", "href": "https://example.com/b"},
                {"title": "既有", "href": "https://example.com/a"},
            ]
        )

        self.assertEqual([item["title"] for item in merged], ["新內容", "既有"])

    def test_invalid_runtime_file_fails_closed(self) -> None:
        self.store.initialize()
        self.store.updates_path.write_text("not json", encoding="utf-8")

        self.assertEqual(self.store.read_updates(), [])

    def test_hero_slides_are_stored_separately(self) -> None:
        slides = [{"src": "https://example.com/a.jpg", "alt": "圖片"}]
        self.store.write_hero_slides(slides)

        self.assertEqual(self.store.read_hero_slides(), slides)
        self.assertTrue((self.data_dir / "generated_hero_slides.json").exists())


if __name__ == "__main__":
    unittest.main()
