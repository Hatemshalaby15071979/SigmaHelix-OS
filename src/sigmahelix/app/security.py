"""Validation for HTTP endpoints that are allowed to receive local user data."""

import ipaddress
from pathlib import Path
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


#: Files larger than this are refused rather than read into memory.
MAX_TEXT_BYTES = 256 * 1024


def confine_to_root(root: Path, raw: str) -> Path:
    """Resolve ``raw`` inside ``root``, refusing anything that escapes it.

    The assistant can propose file operations, so a path from a model is
    treated as untrusted input: relative paths are resolved against the root,
    absolute paths are accepted only when they already sit inside it, and
    symlinks are resolved before the check.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("a path is required")
    base = root.resolve()
    candidate = Path(raw.strip()).expanduser()
    resolved = (candidate if candidate.is_absolute() else base / candidate).resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"path is outside {base}")
    return resolved


def read_text_file(path: Path, limit: int = MAX_TEXT_BYTES) -> str:
    """Read a UTF-8 text file, refusing anything oversized or binary."""
    if path.stat().st_size > limit:
        raise ValueError(f"file is larger than {limit} bytes")
    data = path.read_bytes()
    if b"\x00" in data:
        raise ValueError("file is not text")
    return data.decode("utf-8", "replace")
