"""Authenticated Web Push subscriptions backed by the private SQLite database."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from urllib.parse import urlsplit

from py_vapid import Vapid
from pywebpush import WebPushException, webpush

from app.config import Settings
from app.database import Database


MAX_ENDPOINT_LENGTH = 4096
MAX_KEY_LENGTH = 512
MAX_SUBSCRIPTIONS_PER_USER = 5


class PushError(ValueError):
    pass


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class PushService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    @property
    def private_key_path(self) -> Path:
        return self.settings.data_dir / "vapid_private.pem"

    def _vapid(self) -> Vapid:
        self.settings.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.settings.data_dir, 0o700)
        if self.private_key_path.exists():
            os.chmod(self.private_key_path, 0o600)
            return Vapid.from_file(str(self.private_key_path))

        vapid = Vapid()
        vapid.generate_keys()
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".vapid_private.", suffix=".pem", dir=self.settings.data_dir
        )
        temporary_path = Path(temporary_name)
        try:
            os.close(descriptor)
            vapid.save_key(str(temporary_path))
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.private_key_path)
            os.chmod(self.private_key_path, 0o600)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        return vapid

    def public_key(self) -> str:
        public_numbers = self._vapid().public_key.public_numbers()
        raw = b"\x04"
        raw += public_numbers.x.to_bytes(32, "big")
        raw += public_numbers.y.to_bytes(32, "big")
        return _b64url(raw)

    @staticmethod
    def validate_subscription(subscription: object) -> dict[str, str]:
        if not isinstance(subscription, dict):
            raise PushError("Push subscription must be an object.")
        try:
            endpoint = str(subscription["endpoint"])
            keys = subscription["keys"]
            p256dh = str(keys["p256dh"])
            auth = str(keys["auth"])
        except (KeyError, TypeError) as error:
            raise PushError("Push subscription is missing required fields.") from error
        parsed = urlsplit(endpoint)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or len(endpoint) > MAX_ENDPOINT_LENGTH
        ):
            raise PushError("Push endpoint must be a bounded HTTPS URL.")
        if not p256dh or not auth or len(p256dh) > MAX_KEY_LENGTH or len(auth) > MAX_KEY_LENGTH:
            raise PushError("Push subscription keys are invalid.")
        encoded_size = len(json.dumps(subscription, ensure_ascii=True, separators=(",", ":")))
        if encoded_size > 8192:
            raise PushError("Push subscription is too large.")
        return {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}

    def subscribe(self, user_id: int, subscription: object) -> None:
        values = self.validate_subscription(subscription)
        now = _timestamp()
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT user_id FROM push_subscriptions WHERE endpoint = ?", (values["endpoint"],)
            ).fetchone()
            if existing and existing["user_id"] != user_id:
                raise PushError("This browser subscription belongs to another account.")
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM push_subscriptions WHERE user_id = ?", (user_id,)
            ).fetchone()["count"]
            if not existing and count >= MAX_SUBSCRIPTIONS_PER_USER:
                raise PushError("This account already has the maximum number of push subscriptions.")
            connection.execute(
                """
                INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET p256dh = excluded.p256dh, auth = excluded.auth,
                    updated_at = excluded.updated_at
                """,
                (user_id, values["endpoint"], values["p256dh"], values["auth"], now, now),
            )

    def unsubscribe(self, user_id: int, endpoint: str) -> int:
        if not endpoint or len(endpoint) > MAX_ENDPOINT_LENGTH:
            raise PushError("Push endpoint is invalid.")
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM push_subscriptions WHERE user_id = ? AND endpoint = ?", (user_id, endpoint)
            )
        if cursor.rowcount != 1:
            raise PushError("Push subscription was not found for this account.")
        return cursor.rowcount

    def _send(self, subscription: dict[str, str], title: str, body: str, url: str) -> None:
        payload = json.dumps({"title": title, "body": body, "url": url}, ensure_ascii=False)
        webpush(
            subscription_info={
                "endpoint": subscription["endpoint"],
                "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
            },
            data=payload,
            vapid_private_key=self._vapid(),
            vapid_claims={"sub": self.settings.vapid_subject},
            timeout=20,
            ttl=86400,
        )

    def _send_to_subscriptions(
        self, subscriptions: list[dict[str, str]], title: str, body: str, url: str
    ) -> dict[str, int]:
        sent = 0
        failed = 0
        expired: list[str] = []
        for subscription in subscriptions:
            try:
                self._send(subscription, title, body, url)
                sent += 1
            except WebPushException as error:
                failed += 1
                if getattr(error.response, "status_code", None) in {404, 410}:
                    expired.append(subscription["endpoint"])
            except Exception:
                failed += 1
        if expired:
            with self.database.connect() as connection:
                connection.executemany(
                    "DELETE FROM push_subscriptions WHERE endpoint = ?", ((endpoint,) for endpoint in expired)
                )
        return {"sent": sent, "failed": failed, "subscriptions": len(subscriptions) - len(expired)}

    def send_notification(self, title: str, body: str, url: str = "/#updates") -> dict[str, int]:
        with self.database.connect() as connection:
            subscriptions = [dict(row) for row in connection.execute("SELECT * FROM push_subscriptions")]
        return self._send_to_subscriptions(subscriptions, title, body, url)

    def send_test_to_user(self, user_id: int) -> dict[str, int]:
        with self.database.connect() as connection:
            subscriptions = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM push_subscriptions WHERE user_id = ?", (user_id,)
                )
            ]
        return self._send_to_subscriptions(
            subscriptions, "NMIXX Radar 測試通知", "這是管理者發送的測試通知。", "/#updates"
        )
