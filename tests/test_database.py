from pathlib import Path
import stat
import tempfile
import unittest

from app.config import Settings
from app.database import Database


class DatabaseTests(unittest.TestCase):
    def test_initialization_creates_private_directory_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "runtime"
            settings = Settings.for_test(data_dir)
            database = Database(settings)
            database.initialize()

            self.assertTrue((data_dir / "radar.sqlite3").is_file())
            self.assertEqual(stat.S_IMODE(data_dir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((data_dir / "radar.sqlite3").stat().st_mode), 0o600)

            with database.connect() as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    )
                }
            self.assertTrue(
                {"users", "invitations", "sessions", "push_subscriptions", "rate_limit_events"}
                <= tables
            )

    def test_database_enforces_foreign_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Database(Settings.for_test(Path(directory) / "runtime"))
            database.initialize()
            with database.connect() as connection:
                with self.assertRaisesRegex(Exception, "FOREIGN KEY"):
                    connection.execute(
                        "INSERT INTO sessions "
                        "(id, user_id, token_hash, cookie_kind, created_at, last_seen_at, idle_expires_at, absolute_expires_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        ("session", 999, "hash", "https", "now", "now", "later", "later"),
                    )


if __name__ == "__main__":
    unittest.main()
