import re
import tempfile
import unittest
from pathlib import Path

from app.runtime_data import RuntimeDataStore
from app.site_data import get_site_data
from app.update_watcher import dedupe_items

HAN = re.compile(r"[\u3400-\u9fff]")
HANGUL = re.compile(r"[\uac00-\ud7af]")


class ChineseContentTests(unittest.TestCase):
    def assert_traditional_chinese_user_text(self, value: str) -> None:
        self.assertRegex(value, HAN, f"缺少中文內容：{value!r}")
        self.assertNotRegex(value, HANGUL, f"仍含未翻譯韓文：{value!r}")

    def test_runtime_generated_post_title_is_chinese(self) -> None:
        for item in self.generated_updates():
            self.assert_traditional_chinese_user_text(item["title"])

    def test_runtime_generated_notification_is_chinese(self) -> None:
        for item in self.generated_updates():
            self.assert_traditional_chinese_user_text(item["notification_title"])
            self.assert_traditional_chinese_user_text(item["notification_body"])

    def test_runtime_generated_metadata_contains_no_untranslated_korean(self) -> None:
        for item in self.generated_updates():
            self.assertNotRegex(item["meta"], HANGUL, f"仍含未翻譯韓文：{item['meta']!r}")

    def generated_updates(self) -> list[dict[str, str]]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = RuntimeDataStore(Path(temporary_directory), max_generated_updates=80)
            store.write_updates(
                [{
                    "tag": "公告",
                    "title": "NMIXX 公開新作品資訊",
                    "meta": "2026-09-17 · JYP 官方",
                    "href": "https://nmixx.jype.com/notice",
                    "notification_title": "NMIXX 新作品",
                    "notification_body": "官方公開新作品的發行資訊。",
                }]
            )
            return store.read_updates()

    def test_all_user_facing_site_labels_are_chinese(self) -> None:
        data = get_site_data()
        for item in data["updates"]:
            self.assert_traditional_chinese_user_text(item["title"])
        for _, title in data["schedule"]:
            self.assert_traditional_chinese_user_text(title)
        for release in data["releases"]:
            self.assert_traditional_chinese_user_text(release["type"])
        for member in data["members"]:
            self.assert_traditional_chinese_user_text(member["title"])
            self.assert_traditional_chinese_user_text(member["focus"])
        for slide in data["hero_slides"]:
            self.assert_traditional_chinese_user_text(slide["label"])
            self.assert_traditional_chinese_user_text(slide["source"])

    def test_watcher_rejects_non_chinese_user_facing_content(self) -> None:
        candidate = {
            "tag": "新聞",
            "title": "NMIXX Announces a New Concert",
            "meta": "2026-08-21",
            "href": "https://example.com/new-concert",
            "tone": "blue",
            "should_notify": True,
            "notification_title": "New NMIXX Concert",
            "notification_body": "A new concert has been announced.",
            "notification_reason": "new event",
            "confidence": 0.99,
        }
        self.assertEqual(dedupe_items([candidate]), [])


if __name__ == "__main__":
    unittest.main()
