from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import Settings
from app.database import Database


USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,31}$")
PASSWORD_MINIMUM_LENGTH = 12


class AuthenticationError(ValueError):
    pass


class InvitationError(ValueError):
    pass


class SessionError(ValueError):
    pass


@dataclass(frozen=True)
class User:
    id: int
    username: str
    role: str
    is_active: bool


@dataclass(frozen=True)
class AuthenticatedSession:
    id: str
    token: str
    user: User
    cookie_kind: str
    idle_expires_at: datetime
    absolute_expires_at: datetime
    renewal_required: bool


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Timestamps must include a timezone.")
    return value.astimezone(UTC).isoformat()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


class AuthService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.password_hasher = PasswordHasher()

    def bootstrap_admin(self, now: datetime | None = None) -> User | None:
        current_time = now or datetime.now(UTC)
        with self.database.connect() as connection:
            existing = connection.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
            if existing:
                return None
            if not self.settings.bootstrap_admin_username or not self.settings.bootstrap_admin_password:
                raise ValueError("Bootstrap administrator credentials are required on first startup.")
            return self._create_user(
                connection,
                self.settings.bootstrap_admin_username,
                self.settings.bootstrap_admin_password,
                "admin",
                current_time,
            )

    def get_user_by_username(self, username: str) -> User | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id, username, role, is_active FROM users WHERE username = ?", (username,)
            ).fetchone()
        return self._user_from_row(row) if row else None

    def list_users(self) -> list[User]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT id, username, role, is_active FROM users ORDER BY role DESC, username COLLATE NOCASE"
            ).fetchall()
        return [self._user_from_row(row) for row in rows]

    def set_user_active(self, user_id: int, is_active: bool, now: datetime | None = None) -> None:
        current_time = now or datetime.now(UTC)
        with self.database.connect() as connection:
            target = connection.execute(
                "SELECT role, is_active FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not target:
                raise ValueError("User was not found.")
            if not is_active and target["role"] == "admin" and target["is_active"]:
                active_admin_count = connection.execute(
                    "SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND is_active = 1"
                ).fetchone()["count"]
                if active_admin_count <= 1:
                    raise ValueError("The last active administrator cannot be disabled.")
            connection.execute(
                "UPDATE users SET is_active = ?, updated_at = ? WHERE id = ?",
                (int(is_active), _timestamp(current_time), user_id),
            )
            if not is_active:
                connection.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                    (_timestamp(current_time), user_id),
                )

    def set_password(self, user_id: int, password: str, now: datetime | None = None) -> None:
        if len(password) < PASSWORD_MINIMUM_LENGTH:
            raise ValueError(f"Password must be at least {PASSWORD_MINIMUM_LENGTH} characters.")
        current_time = now or datetime.now(UTC)
        with self.database.connect() as connection:
            target = connection.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if not target:
                raise ValueError("User was not found.")
            connection.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (self.password_hasher.hash(password), _timestamp(current_time), user_id),
            )
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (_timestamp(current_time), user_id),
            )

    def create_invitation(
        self, created_by_user_id: int, now: datetime | None = None, valid_days: int = 7
    ) -> str:
        current_time = now or datetime.now(UTC)
        with self.database.connect() as connection:
            creator = connection.execute(
                "SELECT role, is_active FROM users WHERE id = ?", (created_by_user_id,)
            ).fetchone()
            if not creator or creator["role"] != "admin" or not creator["is_active"]:
                raise InvitationError("Only an active administrator can create invitations.")
            invitation = secrets.token_urlsafe(24)
            connection.execute(
                "INSERT INTO invitations (code_hash, created_by_user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (
                    _token_hash(invitation),
                    created_by_user_id,
                    _timestamp(current_time + timedelta(days=valid_days)),
                    _timestamp(current_time),
                ),
            )
        return invitation

    def register(
        self, invitation: str, username: str, password: str, now: datetime | None = None
    ) -> User:
        current_time = now or datetime.now(UTC)
        with self.database.connect() as connection:
            invitation_row = connection.execute(
                "SELECT id, expires_at, used_at FROM invitations WHERE code_hash = ?", (_token_hash(invitation),)
            ).fetchone()
            if not invitation_row:
                raise InvitationError("Invitation is invalid.")
            if invitation_row["used_at"] or _parse_timestamp(invitation_row["expires_at"]) <= current_time:
                raise InvitationError("Invitation has expired or was already used.")
            user = self._create_user(connection, username, password, "member", current_time)
            connection.execute(
                "UPDATE invitations SET used_at = ?, used_by_user_id = ? WHERE id = ?",
                (_timestamp(current_time), user.id, invitation_row["id"]),
            )
        return user

    def authenticate(
        self, username: str, password: str, cookie_kind: str, now: datetime | None = None
    ) -> AuthenticatedSession:
        current_time = now or datetime.now(UTC)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?",
                (username,),
            ).fetchone()
            if not row or not row["is_active"] or not self._verify_password(row["password_hash"], password):
                raise AuthenticationError("Invalid username or password.")
            user = self._user_from_row(row)
            if self.password_hasher.check_needs_rehash(row["password_hash"]):
                connection.execute(
                    "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                    (self.password_hasher.hash(password), _timestamp(current_time), user.id),
                )
            return self._create_session(connection, user, cookie_kind, current_time)

    def load_session(
        self, token: str, cookie_kind: str, now: datetime | None = None
    ) -> AuthenticatedSession:
        current_time = now or datetime.now(UTC)
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT sessions.id, sessions.cookie_kind, sessions.idle_expires_at, sessions.absolute_expires_at,
                       sessions.revoked_at, users.id AS user_id, users.username, users.role, users.is_active
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = ? AND sessions.cookie_kind = ?
                """,
                (_token_hash(token), cookie_kind),
            ).fetchone()
            if not row or row["revoked_at"] or not row["is_active"]:
                raise SessionError("Session is invalid.")
            idle_expires_at = _parse_timestamp(row["idle_expires_at"])
            absolute_expires_at = _parse_timestamp(row["absolute_expires_at"])
            if current_time >= idle_expires_at or current_time >= absolute_expires_at:
                connection.execute(
                    "UPDATE sessions SET revoked_at = ? WHERE id = ?", (_timestamp(current_time), row["id"])
                )
                raise SessionError("Session has expired.")
            updated_idle_expires_at = min(
                current_time + timedelta(days=self.settings.session_idle_days), absolute_expires_at
            )
            connection.execute(
                "UPDATE sessions SET last_seen_at = ?, idle_expires_at = ? WHERE id = ?",
                (_timestamp(current_time), _timestamp(updated_idle_expires_at), row["id"]),
            )
        return AuthenticatedSession(
            id=row["id"],
            token=token,
            user=User(row["user_id"], row["username"], row["role"], bool(row["is_active"])),
            cookie_kind=row["cookie_kind"],
            idle_expires_at=updated_idle_expires_at,
            absolute_expires_at=absolute_expires_at,
            renewal_required=(absolute_expires_at - current_time)
            <= timedelta(days=self.settings.session_renewal_warning_days),
        )

    def renew_session(
        self, token: str, cookie_kind: str, password: str, now: datetime | None = None
    ) -> AuthenticatedSession:
        current_time = now or datetime.now(UTC)
        current_session = self.load_session(token, cookie_kind, now=current_time)
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT password_hash FROM users WHERE id = ? AND is_active = 1", (current_session.user.id,)
            ).fetchone()
            if not row or not self._verify_password(row["password_hash"], password):
                raise AuthenticationError("Invalid password.")
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE id = ?", (_timestamp(current_time), current_session.id)
            )
            return self._create_session(connection, current_session.user, cookie_kind, current_time)

    def revoke_user_sessions(self, user_id: int, now: datetime | None = None) -> None:
        current_time = now or datetime.now(UTC)
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (_timestamp(current_time), user_id),
            )

    def revoke_session(self, session_id: str, now: datetime | None = None) -> None:
        current_time = now or datetime.now(UTC)
        with self.database.connect() as connection:
            connection.execute(
                "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (_timestamp(current_time), session_id),
            )

    def _create_user(
        self, connection, username: str, password: str, role: str, now: datetime
    ) -> User:
        normalized_username = username.strip()
        if not USERNAME_PATTERN.fullmatch(normalized_username):
            raise ValueError("Username must be 3-32 characters using letters, numbers, underscores, or hyphens.")
        if len(password) < PASSWORD_MINIMUM_LENGTH:
            raise ValueError(f"Password must be at least {PASSWORD_MINIMUM_LENGTH} characters.")
        timestamp = _timestamp(now)
        try:
            cursor = connection.execute(
                "INSERT INTO users (username, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (normalized_username, self.password_hasher.hash(password), role, timestamp, timestamp),
            )
        except Exception as error:
            if "UNIQUE" in str(error).upper():
                raise ValueError("Username is already in use.") from error
            raise
        return User(cursor.lastrowid, normalized_username, role, True)

    def _create_session(self, connection, user: User, cookie_kind: str, now: datetime) -> AuthenticatedSession:
        if cookie_kind not in {"https", "lan"}:
            raise ValueError("Unsupported session cookie kind.")
        token = secrets.token_urlsafe(32)
        session_id = secrets.token_urlsafe(18)
        idle_expires_at = now + timedelta(days=self.settings.session_idle_days)
        absolute_expires_at = now + timedelta(days=self.settings.session_absolute_days)
        connection.execute(
            """
            INSERT INTO sessions
            (id, user_id, token_hash, cookie_kind, created_at, last_seen_at, idle_expires_at, absolute_expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                user.id,
                _token_hash(token),
                cookie_kind,
                _timestamp(now),
                _timestamp(now),
                _timestamp(idle_expires_at),
                _timestamp(absolute_expires_at),
            ),
        )
        return AuthenticatedSession(
            id=session_id,
            token=token,
            user=user,
            cookie_kind=cookie_kind,
            idle_expires_at=idle_expires_at,
            absolute_expires_at=absolute_expires_at,
            renewal_required=False,
        )

    def _verify_password(self, password_hash: str, password: str) -> bool:
        try:
            return self.password_hasher.verify(password_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False

    @staticmethod
    def _user_from_row(row) -> User:
        return User(row["id"], row["username"], row["role"], bool(row["is_active"]))
