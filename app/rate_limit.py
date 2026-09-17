from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.database import Database


class RateLimiter:
    """A small SQLite sliding-window limiter suitable for this private, small-user app."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def allow(
        self,
        scope: str,
        subject: str,
        *,
        limit: int,
        window_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("Rate limit values must be positive.")
        current_time = now or datetime.now(UTC)
        cutoff = current_time - timedelta(seconds=window_seconds)
        with self.database.connect() as connection:
            connection.execute(
                "DELETE FROM rate_limit_events WHERE scope = ? AND subject = ? AND created_at < ?",
                (scope, subject, cutoff.isoformat()),
            )
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM rate_limit_events WHERE scope = ? AND subject = ?",
                (scope, subject),
            ).fetchone()["count"]
            if count >= limit:
                return False
            connection.execute(
                "INSERT INTO rate_limit_events (scope, subject, created_at) VALUES (?, ?, ?)",
                (scope, subject, current_time.isoformat()),
            )
        return True
