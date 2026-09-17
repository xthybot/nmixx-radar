from __future__ import annotations

from urllib.parse import urlsplit

ALLOWED_EXTERNAL_HOSTS = frozenset(
    {
        "nmixx.jype.com",
        "www.youtube.com",
        "youtube.com",
        "www.instagram.com",
        "news.google.com",
    }
)


def is_allowed_external_url(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname in ALLOWED_EXTERNAL_HOSTS
        and not parsed.username
        and not parsed.password
    )
