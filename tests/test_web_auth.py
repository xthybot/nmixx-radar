from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class WebAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.settings = Settings.for_test(Path(self.temporary_directory.name) / "runtime")
        self.client = TestClient(create_app(self.settings), base_url="https://radar.test")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_home_requires_login_then_accepts_bootstrap_administrator(self) -> None:
        anonymous = self.client.get("/", follow_redirects=False)
        login = self.client.post(
            "/login",
            data={"username": "admin", "password": "test-password-not-for-production"},
            follow_redirects=False,
        )
        authenticated = self.client.get("/", follow_redirects=False)

        self.assertEqual(anonymous.status_code, 303)
        self.assertEqual(anonymous.headers["location"], "/login")
        self.assertEqual(login.status_code, 303)
        self.assertIn("radar_https_session", login.headers["set-cookie"])
        self.assertEqual(authenticated.status_code, 200)

    def test_admin_can_create_single_use_invitation_over_https(self) -> None:
        self.client.post(
            "/login",
            data={"username": "admin", "password": "test-password-not-for-production"},
            follow_redirects=False,
        )
        response = self.client.post("/admin/invitations", follow_redirects=False)

        self.assertEqual(response.status_code, 201)
        self.assertIn("invitation_code", response.json())

    def test_invited_member_can_register_and_log_in(self) -> None:
        self.client.post(
            "/login",
            data={"username": "admin", "password": "test-password-not-for-production"},
            follow_redirects=False,
        )
        invitation = self.client.post("/admin/invitations").json()["invitation_code"]
        member_client = TestClient(create_app(self.settings), base_url="https://radar.test")
        registration = member_client.post(
            "/register",
            data={
                "invitation_code": invitation,
                "username": "member",
                "password": "member-password-2026",
            },
            follow_redirects=False,
        )

        self.assertEqual(registration.status_code, 303)
        self.assertIn("radar_https_session", registration.headers["set-cookie"])
        self.assertEqual(member_client.get("/", follow_redirects=False).status_code, 200)


if __name__ == "__main__":
    unittest.main()
