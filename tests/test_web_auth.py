import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

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

    def test_near_expiry_session_shows_renewal_prompt_and_rotates_after_password_check(self) -> None:
        self.client.post(
            "/login",
            data={"username": "admin", "password": "test-password-not-for-production"},
            follow_redirects=False,
        )
        token = self.client.cookies.get("radar_https_session")
        assert token is not None
        old_session = self.client.app.state.auth.load_session(token, "https")
        warning_time = datetime.now(UTC) + timedelta(days=10)
        with self.client.app.state.database.connect() as connection:
            connection.execute(
                "UPDATE sessions SET absolute_expires_at = ? WHERE id = ?",
                (warning_time.isoformat(), old_session.id),
            )

        page = self.client.get("/")
        renewal = self.client.post(
            "/account/renew",
            data={"password": "test-password-not-for-production"},
            follow_redirects=False,
        )

        self.assertIn("重新驗證", page.text)
        self.assertEqual(renewal.status_code, 303)
        self.assertNotEqual(self.client.cookies.get("radar_https_session"), token)

    def test_push_management_requires_https_and_binds_to_logged_in_user(self) -> None:
        self.client.post(
            "/login",
            data={"username": "admin", "password": "test-password-not-for-production"},
            follow_redirects=False,
        )
        invitation = self.client.post("/admin/invitations").json()["invitation_code"]
        member_client = TestClient(create_app(self.settings), base_url="https://radar.test")
        member_client.post(
            "/register",
            data={
                "invitation_code": invitation,
                "username": "member",
                "password": "member-password-2026",
            },
            follow_redirects=False,
        )
        subscription = {
            "endpoint": "https://push.example.test/subscription/opaque-token",
            "keys": {"p256dh": "public-key", "auth": "auth-key"},
        }

        self.assertEqual(member_client.get("/api/push/public-key").status_code, 200)
        self.assertEqual(member_client.post("/api/push/subscribe", json=subscription).status_code, 201)
        with self.client.app.state.database.connect() as connection:
            owner = connection.execute(
                "SELECT user_id FROM push_subscriptions WHERE endpoint = ?", (subscription["endpoint"],)
            ).fetchone()
        self.assertEqual(owner["user_id"], 2)
        public_client = TestClient(create_app(self.settings), base_url="http://radar.test")
        self.assertEqual(public_client.get("/api/push/public-key").status_code, 403)

    def test_admin_can_reset_member_password_and_revoke_member_sessions(self) -> None:
        self.client.post(
            "/login",
            data={"username": "admin", "password": "test-password-not-for-production"},
            follow_redirects=False,
        )
        invitation = self.client.post("/admin/invitations").json()["invitation_code"]
        member_client = TestClient(create_app(self.settings), base_url="https://radar.test")
        member_client.post(
            "/register",
            data={
                "invitation_code": invitation,
                "username": "member",
                "password": "member-password-2026",
            },
            follow_redirects=False,
        )
        member = self.client.app.state.auth.get_user_by_username("member")
        assert member is not None

        reset = self.client.post(
            f"/admin/users/{member.id}/password",
            data={"password": "member-password-reset-2026"},
            follow_redirects=False,
        )

        self.assertEqual(self.client.get("/admin").status_code, 200)
        self.assertEqual(reset.status_code, 303)
        self.assertEqual(member_client.get("/", follow_redirects=False).status_code, 303)
        login = member_client.post(
            "/login",
            data={"username": "member", "password": "member-password-reset-2026"},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 303)

    def test_https_state_changing_request_rejects_a_foreign_browser_origin(self) -> None:
        self.client.post(
            "/login",
            data={"username": "admin", "password": "test-password-not-for-production"},
            follow_redirects=False,
        )

        response = self.client.post("/admin/invitations", headers={"origin": "https://attacker.example"})

        self.assertEqual(response.status_code, 403)

    def test_lan_http_allows_login_but_not_invitation_registration(self) -> None:
        lan_client = TestClient(
            create_app(self.settings),
            base_url="http://radar.test",
            client=("192.168.1.20", 50000),
        )

        login = lan_client.post(
            "/login",
            data={"username": "admin", "password": "test-password-not-for-production"},
            follow_redirects=False,
        )

        self.assertEqual(login.status_code, 303)
        self.assertIn("radar_lan_session", login.headers["set-cookie"])
        self.assertEqual(
            lan_client.post(
                "/register",
                data={"invitation_code": "unused", "username": "member", "password": "member-password-2026"},
            ).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
