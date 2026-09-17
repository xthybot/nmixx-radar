from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from app.auth import AuthService, SessionError
from app.config import Settings
from app.database import Database


class SessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        settings = Settings.for_test(Path(self.temporary_directory.name) / "runtime")
        self.settings = settings
        self.database = Database(settings)
        self.database.initialize()
        self.service = AuthService(self.database, settings)
        self.now = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)
        self.service.bootstrap_admin(now=self.now)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_active_session_extends_idle_deadline_without_extending_absolute_deadline(self) -> None:
        created = self.service.authenticate(
            "admin", "test-password-not-for-production", "https", now=self.now
        )
        later = self.now + timedelta(days=10)
        loaded = self.service.load_session(created.token, "https", now=later)

        self.assertEqual(loaded.absolute_expires_at, created.absolute_expires_at)
        self.assertEqual(loaded.idle_expires_at, later + timedelta(days=self.settings.session_idle_days))

    def test_near_absolute_expiry_requires_renewal_and_rotation_resets_lifetime(self) -> None:
        created = self.service.authenticate(
            "admin", "test-password-not-for-production", "https", now=self.now
        )
        warning_time = created.absolute_expires_at - timedelta(days=10)
        for day in range(20, 161, 20):
            self.service.load_session(created.token, "https", now=self.now + timedelta(days=day))
        loaded = self.service.load_session(created.token, "https", now=warning_time)
        renewed = self.service.renew_session(
            created.token,
            "https",
            "test-password-not-for-production",
            now=warning_time,
        )

        self.assertTrue(loaded.renewal_required)
        self.assertNotEqual(renewed.token, created.token)
        self.assertEqual(
            renewed.absolute_expires_at,
            warning_time + timedelta(days=self.settings.session_absolute_days),
        )
        with self.assertRaises(SessionError):
            self.service.load_session(created.token, "https", now=warning_time)

    def test_expired_session_is_rejected_without_deleting_user(self) -> None:
        created = self.service.authenticate(
            "admin", "test-password-not-for-production", "https", now=self.now
        )
        with self.assertRaises(SessionError):
            self.service.load_session(
                created.token, "https", now=created.absolute_expires_at + timedelta(seconds=1)
            )
        self.assertEqual(self.service.get_user_by_username("admin").role, "admin")


if __name__ == "__main__":
    unittest.main()
