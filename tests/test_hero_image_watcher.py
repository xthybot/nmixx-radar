from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from app.hero_image_watcher import run_once
from app.runtime_data import RuntimeDataStore


class HeroImageWatcherTests(unittest.TestCase):
    def test_timer_uses_configured_interval_instead_of_a_fixed_daily_rule(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = RuntimeDataStore(root / "data", max_generated_updates=80)
            store.initialize()
            (store.data_dir / "hero_slides_state.json").write_text(
                '{"checked_at": "' + datetime.now(UTC).isoformat() + '"}', encoding="utf-8"
            )
            with patch("app.hero_image_watcher.fetch_html") as fetch_html:
                self.assertEqual(
                    run_once(runtime_data=store, minimum_interval_seconds=3600),
                    0,
                )
            fetch_html.assert_not_called()

    def test_gallery_slides_are_written_to_runtime_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            store = RuntimeDataStore(root / "data", max_generated_updates=80)
            html = 'https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/galleries/new.jpg'
            with patch("app.hero_image_watcher.fetch_html", return_value=html):
                self.assertEqual(
                    run_once(runtime_data=store, force=True),
                    0,
                )

            self.assertEqual(store.read_hero_slides()[0]["src"], "https://d1al7qj7ydfbpt.cloudfront.net/artists/nmixx/galleries/new.jpg")
            self.assertFalse((root / "app" / "generated_hero_slides.py").exists())


if __name__ == "__main__":
    unittest.main()
