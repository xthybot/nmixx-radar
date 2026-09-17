import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from app.auth import AuthenticationError, AuthService, InvitationError, SessionError
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

        invitation = self.service.create_invitation(admin.id, now=self.now)
        member = self.service.register(invitation, "member", "member-password-2026", now=self.now)
        self.service.set_user_active(member.id, False, now=self.now)
        with self.assertRaises(AuthenticationError):
            self.service.authenticate(
                "member", "member-password-2026", "https", now=self.now
            )

    def test_password_reset_revokes_sessions_and_uses_the_new_password(self) -> None:
        admin = self.service.bootstrap_admin(now=self.now)
        assert admin is not None
        session = self.service.authenticate(
            "admin", "test-password-not-for-production", "https", now=self.now
        )

        self.service.set_password(admin.id, "new-password-for-admin", now=self.now)

        with self.assertRaises(AuthenticationError):
            self.service.authenticate("admin", "test-password-not-for-production", "https", now=self.now)
        with self.assertRaises(SessionError):
            self.service.load_session(session.token, "https", now=self.now)
        self.assertTrue(
            self.service.authenticate("admin", "new-password-for-admin", "https", now=self.now).token
        )

    def test_last_active_administrator_cannot_be_disabled(self) -> None:
        admin = self.service.bootstrap_admin(now=self.now)
        assert admin is not None

        with self.assertRaises(ValueError):
            self.service.set_user_active(admin.id, False, now=self.now)


if __name__ == "__main__":
    unittest.main()
