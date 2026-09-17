from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

SAMPLE_BOOTSTRAP_PASSWORD = "change-me-before-first-start"


def _int_setting(values: Mapping[str, str], name: str, default: int) -> int:
    raw = values.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer.") from error
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def _bool_setting(values: Mapping[str, str], name: str, default: bool) -> bool:
    raw = values.get(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false.")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    app_host: str
    app_port: int
    public_base_url: str
    bootstrap_admin_username: str
    bootstrap_admin_password: str
    allow_lan_http_login: bool
    trusted_proxy_ips: tuple[str, ...]
    session_idle_days: int
    session_absolute_days: int
    session_renewal_warning_days: int
    update_interval_seconds: int
    hero_update_interval_seconds: int
    max_generated_updates: int
    max_image_cache_bytes: int
    ollama_host: str
    ollama_model: str
    ai_review_command: str
    openai_api_key: str
    openai_model: str
    vapid_subject: str

    @property
    def database_path(self) -> Path:
        return self.data_dir / "radar.sqlite3"

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> Settings:
        load_dotenv(override=False)
        source = os.environ if values is None else values
        data_dir = Path(source.get("DATA_DIR", "./data")).expanduser()
        password = source.get("BOOTSTRAP_ADMIN_PASSWORD", "").strip()
        if password == SAMPLE_BOOTSTRAP_PASSWORD:
            raise ValueError("BOOTSTRAP_ADMIN_PASSWORD must be changed before first start.")
        trusted_proxy_ips = tuple(
            item.strip() for item in source.get("TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",") if item.strip()
        )
        return cls(
            data_dir=data_dir,
            app_host=source.get("APP_HOST", "0.0.0.0").strip(),
            app_port=_int_setting(source, "APP_PORT", 32765),
            public_base_url=source.get("PUBLIC_BASE_URL", "").rstrip("/"),
            bootstrap_admin_username=source.get("BOOTSTRAP_ADMIN_USERNAME", "").strip(),
            bootstrap_admin_password=password,
            allow_lan_http_login=_bool_setting(source, "ALLOW_LAN_HTTP_LOGIN", True),
            trusted_proxy_ips=trusted_proxy_ips,
            session_idle_days=_int_setting(source, "SESSION_IDLE_DAYS", 30),
            session_absolute_days=_int_setting(source, "SESSION_ABSOLUTE_DAYS", 180),
            session_renewal_warning_days=_int_setting(source, "SESSION_RENEWAL_WARNING_DAYS", 14),
            update_interval_seconds=_int_setting(source, "UPDATE_INTERVAL_SECONDS", 900),
            hero_update_interval_seconds=_int_setting(source, "HERO_UPDATE_INTERVAL_SECONDS", 86400),
            max_generated_updates=_int_setting(source, "MAX_GENERATED_UPDATES", 80),
            max_image_cache_bytes=_int_setting(source, "MAX_IMAGE_CACHE_BYTES", 268435456),
            ollama_host=source.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=source.get("OLLAMA_MODEL", "").strip(),
            ai_review_command=source.get("AI_REVIEW_COMMAND", "").strip(),
            openai_api_key=source.get("OPENAI_API_KEY", "").strip(),
            openai_model=source.get("OPENAI_MODEL", "").strip(),
            vapid_subject=source.get("VAPID_SUBJECT", "mailto:admin@example.com").strip(),
        )

    @classmethod
    def for_test(cls, data_dir: Path) -> Settings:
        return cls.from_env(
            {
                "DATA_DIR": str(data_dir),
                "BOOTSTRAP_ADMIN_USERNAME": "admin",
                "BOOTSTRAP_ADMIN_PASSWORD": "test-password-not-for-production",
                "PUBLIC_BASE_URL": "https://radar.test",
            }
        )
