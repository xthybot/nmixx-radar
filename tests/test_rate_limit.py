from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from app.config import Settings
from app.database import Database
from app.rate_limit import RateLimiter


class RateLimiterTests(unittest.TestCase):
    def test_limits_events_inside_a_sliding_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = Settings.for_test(Path(temporary_directory) / "runtime")
            database = Database(settings)
            database.initialize()
            limiter = RateLimiter(database)
            now = datetime(2026, 9, 17, tzinfo=UTC)

            self.assertTrue(limiter.allow("push", "user-1", limit=2, window_seconds=60, now=now))
            self.assertTrue(limiter.allow("push", "user-1", limit=2, window_seconds=60, now=now))
            self.assertFalse(limiter.allow("push", "user-1", limit=2, window_seconds=60, now=now))
            self.assertTrue(
                limiter.allow("push", "user-1", limit=2, window_seconds=60, now=now + timedelta(seconds=61))
            )


if __name__ == "__main__":
    unittest.main()
