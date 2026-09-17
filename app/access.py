from __future__ import annotations

from enum import StrEnum
import ipaddress

from fastapi import Request

from app.config import Settings


class Transport(StrEnum):
    HTTPS = "https"
    LAN_HTTP = "lan_http"
    PUBLIC_HTTP = "public_http"


def classify_transport(
    peer_ip: str | None, scheme: str, forwarded_proto: str | None, settings: Settings
) -> Transport:
    normalized_peer = peer_ip or ""
    trusted_proxy = normalized_peer in settings.trusted_proxy_ips
    if scheme == "https" or (trusted_proxy and forwarded_proto == "https"):
        return Transport.HTTPS
    if settings.allow_lan_http_login and _is_private_peer(normalized_peer):
        return Transport.LAN_HTTP
    return Transport.PUBLIC_HTTP


def request_transport(request: Request, settings: Settings) -> Transport:
    peer_ip = request.client.host if request.client else None
    return classify_transport(
        peer_ip,
        request.url.scheme,
        request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower() or None,
        settings,
    )


def _is_private_peer(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.is_private or address.is_loopback or address.is_link_local
