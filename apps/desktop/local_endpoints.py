"""Validation for HTTP endpoints that are allowed to receive local user data."""
import ipaddress
from urllib.parse import urlsplit


def is_loopback_url(value: str) -> bool:
    """Accept only credential-free HTTP(S) URLs on localhost/loopback IPs."""
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.username is not None or parsed.password is not None:
            return False
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname.lower() == "localhost":
            return True
        return ipaddress.ip_address(hostname).is_loopback
    except (ValueError, TypeError):
        return False
