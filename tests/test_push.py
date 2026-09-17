from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from app.auth import AuthService
from app.config import Settings
from app.database import Database
from app.push import PushError, PushService


VALID_SUBSCRIPTION = {
    "endpoint": "https://push.example.test/subscription/opaque-token",
    "keys": {
        "p256dh": "BK-8R67xOT9tlyp2YKUjcIaD9RBbJ4SpC9W2BpENZQbZ5-Xv0EQmI4_BFql6IMlNPnSSoAU-5IMnTqiP5Rk0PjA",
        "auth": "abcdefghijklmnopqrstuv",
    },
}


class PushServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.settings = Settings.for_test(Path(self.temporary_directory.name) / "runtime")
        self.database = Database(self.settings)
        self.database.initialize()
        self.auth = AuthService(self.database, self.settings)
        self.admin = self.auth.bootstrap_admin()
        assert self.admin is not None
        self.member = self.auth.register(
            self.auth.create_invitation(self.admin.id), "member", "member-password-2026"
        )
        self.push = PushService(self.database, self.settings)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_subscription_is_owned_by_the_authenticated_user(self) -> None:
        self.push.subscribe(self.member.id, VALID_SUBSCRIPTION)

        with self.assertRaises(PushError):
            self.push.unsubscribe(self.admin.id, VALID_SUBSCRIPTION["endpoint"])

        self.assertEqual(self.push.unsubscribe(self.member.id, VALID_SUBSCRIPTION["endpoint"]), 1)

    def test_subscription_schema_and_size_are_validated(self) -> None:
        with self.assertRaises(PushError):
            self.push.subscribe(self.member.id, {"endpoint": "http://not-secure.example"})

        with self.assertRaises(PushError):
            self.push.subscribe(
                self.member.id,
                {**VALID_SUBSCRIPTION, "endpoint": "https://push.example/" + "x" * 5000},
            )

    def test_vapid_private_key_is_created_in_the_private_runtime_directory(self) -> None:
        self.assertTrue(self.push.public_key())
        private_key = self.settings.data_dir / "vapid_private.pem"

        self.assertTrue(private_key.exists())
        self.assertEqual(private_key.stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
