from datetime import UTC, datetime, timedelta
from pathlib import Path
import tempfile
import unittest

from app.auth import AuthService, AuthenticationError, InvitationError
from app.config import Settings
from app.database import Database


class AuthServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        settings = Settings.for_test(Path(self.temporary_directory.name) / "runtime")
        self.database = Database(settings)
        self.database.initialize()
        self.service = AuthService(self.database, settings)
        self.now = datetime(2026, 9, 17, 8, 0, tzinfo=UTC)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_bootstrap_admin_is_created_once_and_can_authenticate(self) -> None:
        created = self.service.bootstrap_admin(now=self.now)
        second_attempt = self.service.bootstrap_admin(now=self.now)
        authenticated = self.service.authenticate(
            "admin", "test-password-not-for-production", "https", now=self.now
        )

        self.assertIsNotNone(created)
        self.assertIsNone(second_attempt)
        self.assertEqual(authenticated.user.role, "admin")
        self.assertTrue(authenticated.token)

    def test_invitation_can_be_used_only_once(self) -> None:
        admin = self.service.bootstrap_admin(now=self.now)
        assert admin is not None
        invitation = self.service.create_invitation(admin.id, now=self.now)
        member = self.service.register(
            invitation, "member", "member-password-2026", now=self.now
        )

        self.assertEqual(member.role, "member")
        with self.assertRaises(InvitationError):
            self.service.register(invitation, "other", "other-password-2026", now=self.now)

    def test_authentication_rejects_wrong_password_and_inactive_user(self) -> None:
        admin = self.service.bootstrap_admin(now=self.now)
        assert admin is not None
        with self.assertRaises(AuthenticationError):
            self.service.authenticate("admin", "wrong-password", "https", now=self.now)

        self.service.set_user_active(admin.id, False, now=self.now)
        with self.assertRaises(AuthenticationError):
            self.service.authenticate(
                "admin", "test-password-not-for-production", "https", now=self.now
            )


if __name__ == "__main__":
    unittest.main()
