from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.runtime_data import RuntimeDataStore
from app.update_watcher import review_with_command, run_once


class UpdateWatcherTests(unittest.TestCase):
    def test_timer_respects_configured_minimum_interval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = root / "sources.json"
            config_path.write_text(
                json.dumps({"sources": [{"name": "JYP", "url": "https://nmixx.jype.com", "tag": "公告", "tone": "lime"}]}),
                encoding="utf-8",
            )
            store = RuntimeDataStore(root / "data", max_generated_updates=80)
            store.initialize()
            (store.data_dir / "update_state.json").write_text(
                json.dumps({"last_run_at": datetime.now(UTC).isoformat(), "sources": {}, "events": []}),
                encoding="utf-8",
            )
            with patch("app.update_watcher.fetch_source") as fetch_source:
                self.assertEqual(
                    run_once(config_path, runtime_data=store, minimum_interval_seconds=900),
                    0,
                )
            fetch_source.assert_not_called()

    def test_new_items_are_written_to_runtime_json_not_the_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            config_path = root / "sources.json"
            config_path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "name": "JYP NMIXX Notice",
                                "url": "https://nmixx.jype.com/Mobile/NoticeList",
                                "tag": "公告",
                                "tone": "lime",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            store = RuntimeDataStore(root / "data", max_generated_updates=80)
            store.initialize()
            (store.data_dir / "update_state.json").write_text(
                json.dumps(
                    {
                        "sources": {
                            "https://nmixx.jype.com/Mobile/NoticeList": {
                                "name": "JYP NMIXX Notice",
                                "hash": "old",
                                "text": "old text",
                            }
                        },
                        "events": [],
                    }
                ),
                encoding="utf-8",
            )
            candidate = {
                "tag": "公告",
                "title": "NMIXX 公開最新公告",
                "meta": "2026-09-17 · JYP 官方",
                "href": "https://nmixx.jype.com/Mobile/NoticeView?AnSeq=1",
                "tone": "lime",
                "should_notify": True,
                "notification_title": "NMIXX 最新公告",
                "notification_body": "官方公開最新活動公告。",
                "notification_reason": "test",
                "confidence": 0.99,
            }
            push_service = Mock()
            push_service.send_notification.return_value = {"sent": 0, "failed": 0, "subscriptions": 0}
            with (
                patch("app.update_watcher.fetch_source", return_value=("new", "new text")),
                patch("app.update_watcher.review_change", return_value={"is_new": True, "items": [candidate]}),
            ):
                self.assertEqual(run_once(config_path, runtime_data=store, push_service=push_service), 1)

            self.assertEqual(store.read_updates()[0]["title"], "NMIXX 公開最新公告")
            self.assertFalse((config_path.parent / "app" / "generated_updates.py").exists())

    @patch("app.update_watcher.subprocess.run")
    def test_ai_command_is_an_argument_list_without_a_shell(self, run_mock) -> None:
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = '{"is_new": false, "items": [], "reason": "ok"}'

        review_with_command('reviewer --model "local model"', {"hello": "world"})

        command, = run_mock.call_args.args
        self.assertEqual(command, ["reviewer", "--model", "local model"])
        self.assertFalse(run_mock.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
