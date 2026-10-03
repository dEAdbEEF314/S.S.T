import re
import socket
import ipaddress
import urllib.parse
from pathlib import Path
from typing import Optional, List, Tuple

def normalize_path(win_path: str) -> Path:
    r"""
    Converts a Windows-style path (C:\...) to a WSL2 mount path (/mnt/c/...).
    If the path is already a valid path, it returns it as a Path object.
    """
    if not win_path:
        return Path()

    # 1. Check if it's already a WSL path (starts with /)
    if win_path.startswith('/'):
        return Path(win_path)

    # 2. Handle Windows Drive Letter (e.g., C:\...)
    match = re.match(r'^([a-zA-Z]):\\?(.*)', win_path)
    if match:
        drive = match.group(1).lower()
        remainder = match.group(2).replace('\\', '/')
        return Path(f"/mnt/{drive}/{remainder}")

    # 3. If it doesn't match a drive letter, just normalize slashes
    return Path(win_path.replace('\\', '/'))


def ensure_path(any_path: str) -> Path:
    """Ensures the path is usable in the current environment."""
    return normalize_path(any_path)


def is_safe_subpath(target_path: Path, base_dir: Path) -> bool:
    """
    Verifies that target_path is located strictly inside base_dir
    to prevent path traversal vulnerabilities.
    """
    try:
        resolved_target = target_path.resolve()
        resolved_base = base_dir.resolve()
        return resolved_target.is_relative_to(resolved_base)
    except Exception:
        return False


def is_private_ip(ip_or_host: str) -> bool:
    """
    Determines whether an IP address or hostname belongs to private,
    loopback, link-local, multicast, or reserved ranges (SSRF prevention).
    """
    if not ip_or_host:
        return True

    # Strip port or brackets if present (e.g. [::1]:8080 or localhost:8080)
    cleaned_host = ip_or_host.strip().lower()
    if cleaned_host.startswith("[") and "]" in cleaned_host:
        cleaned_host = cleaned_host[1:cleaned_host.index("]")]
    elif ":" in cleaned_host and cleaned_host.count(":") == 1:
        cleaned_host = cleaned_host.split(":")[0]

    # Quick check for known local hostnames
    if cleaned_host in {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}:
        return True

    # Try direct IP parsing first
    try:
        ip = ipaddress.ip_address(cleaned_host)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        )
    except ValueError:
        pass

    # If it's a hostname, resolve it to verify all mapped IP addresses
    try:
        addr_info = socket.getaddrinfo(cleaned_host, None)
        for entry in addr_info:
            sockaddr = entry[4]
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
                if (
                    ip.is_private
                    or ip.is_loopback
                    or ip.is_link_local
                    or ip.is_multicast
                    or ip.is_reserved
                    or ip.is_unspecified
                ):
                    return True
            except ValueError:
                return True
        return False
    except (socket.gaierror, OSError):
        # Unresolvable hostname is considered potentially unsafe / rejected
        return True


def safe_validate_url(url: Optional[str], block_private: bool = True) -> Tuple[bool, str]:
    """
    Validates a URL for safe HTTP/HTTPS requests (SSRF mitigation).
    Returns (is_valid, reason).
    """
    if not url:
        return False, "URL is empty"

    url_str = str(url).strip()
    try:
        parsed = urllib.parse.urlparse(url_str)
    except Exception as e:
        return False, f"Malformed URL: {e}"

    if parsed.scheme.lower() not in {"http", "https"}:
        return False, f"Unsupported scheme: '{parsed.scheme}'. Only http and https are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "Missing hostname in URL"

    if block_private and is_private_ip(hostname):
        return False, f"Destination hostname/IP '{hostname}' is classified as private or restricted (SSRF guard)."

    return True, "OK"


def mask_secret(secret: Optional[str], show_prefix: int = 4, show_suffix: int = 4) -> str:
    """
    Masks a sensitive string (API key, token, credential) for safe display/logging.
    Example: 'sk-1234567890abcdef' -> 'sk-1...cdef'
    """
    if not secret:
        return ""
    secret_str = str(secret).strip()
    if len(secret_str) <= (show_prefix + show_suffix + 2):
        return "***"
    return f"{secret_str[:show_prefix]}...{secret_str[-show_suffix:]}"


_WEBHOOK_URL_PATTERN = re.compile(r'https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/(\d+)/([\w-]+)', re.IGNORECASE)
_GENERIC_KEY_PATTERN = re.compile(r'(?i)(api[_-]?key|bearer|token|secret|password|steam_login_secure)[\s:=]+([a-zA-Z0-9_\-\.]{8,})')

def sanitize_log_text(text: str, secrets: Optional[List[str]] = None) -> str:
    """
    Sanitizes log messages or error text by redacting known secrets and
    common sensitive patterns (such as Discord webhook URLs and API keys).
    """
    if not text:
        return ""

    sanitized = str(text)

    # 1. Mask explicitly provided secret strings
    if secrets:
        for s in secrets:
            if s and len(str(s).strip()) >= 4:
                sanitized = sanitized.replace(str(s), "[REDACTED]")

    # 2. Mask Discord Webhook tokens
    sanitized = _WEBHOOK_URL_PATTERN.sub(r'https://discord.com/api/webhooks/\1/[REDACTED_WEBHOOK_TOKEN]', sanitized)

    # 3. Mask generic API keys or secrets in logs
    sanitized = _GENERIC_KEY_PATTERN.sub(r'\1: [REDACTED]', sanitized)

    return sanitized
