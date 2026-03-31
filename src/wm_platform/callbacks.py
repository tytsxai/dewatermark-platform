from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from wm_platform.config import Settings
from wm_platform.errors import AppError


def validate_callback_url(raw_url: str, settings: Settings) -> str:
    url = raw_url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise AppError("VALIDATION_ERROR", "callback_url must use http or https", 400)
    if not parsed.netloc or not parsed.hostname:
        raise AppError("VALIDATION_ERROR", "callback_url must include a host", 400)
    if settings.allow_private_callback_urls:
        return url

    host = parsed.hostname.strip().lower()
    if host == "localhost":
        raise AppError("VALIDATION_ERROR", "callback_url host is not allowed", 400)

    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return url

    if (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    ):
        raise AppError("VALIDATION_ERROR", "callback_url host is not allowed", 400)
    return url
