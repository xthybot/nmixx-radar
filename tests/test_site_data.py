from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from app.runtime_data import RuntimeDataStore
from app.site_data import get_site_data


class SiteDataTests(unittest.TestCase):
    def test_runtime_json_is_used_without_reloading_source_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = RuntimeDataStore(Path(temporary_directory), max_generated_updates=80)
            store.write_updates([{"title": "動態更新", "href": "https://nmixx.jype.com/Mobile/NoticeView?AnSeq=1"}])
            store.write_hero_slides(
                [{"src": "https://example.com/hero.jpg", "alt": "最新圖片", "label": "最新", "source": "JYP"}]
            )

            site_data = get_site_data(store)

        self.assertEqual(site_data["updates"][0]["title"], "動態更新")
        self.assertEqual(site_data["hero_slides"][0]["src"], "https://example.com/hero.jpg")


if __name__ == "__main__":
    unittest.main()
