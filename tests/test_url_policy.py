from __future__ import annotations

import unittest

from app.site_data import get_site_data
from app.update_watcher import dedupe_items
from app.url_policy import is_allowed_external_url


class ExternalUrlPolicyTests(unittest.TestCase):
    def test_site_links_are_https_and_allowlisted(self) -> None:
        data = get_site_data()
        links = [item["href"] for item in data["updates"]]
        links.extend(item["href"] for item in data["releases"])
        links.extend(item["href"] for item in data["official_channels"])

        for url in links:
            with self.subTest(url=url):
                self.assertTrue(is_allowed_external_url(url))

    def test_untrusted_ai_link_is_dropped(self) -> None:
        candidate = {
            "tag": "新聞",
            "title": "NMIXX 發布新的演出消息",
            "meta": "2026-09-17 · 新聞 RSS",
            "href": "javascript:alert(1)",
            "tone": "blue",
            "should_notify": True,
            "notification_title": "NMIXX 新演出",
            "notification_body": "有新的演出消息。",
            "confidence": 0.99,
        }

        self.assertEqual(dedupe_items([candidate]), [])


if __name__ == "__main__":
    unittest.main()
