"""Remove local identity and credentials before constructing public report text.

The browser requests a prefilled issue URL before anyone submits the issue.
Keep this boundary independent of Tk so every report serializer can use it.
"""
from __future__ import annotations

import os
import re
import ipaddress
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


def public_text(value, paths=()) -> str:
    """Keep diagnostic messages while removing common private path/URL data."""
    text = str(value or "")
    roots = [str(p) for p in paths if p]
    roots += [os.environ.get(key, "") for key in ("USERPROFILE", "HOME", "LOCALAPPDATA", "APPDATA")]
    roots.append(str(Path.home()))
    for root in sorted(set(filter(None, roots)), key=len, reverse=True):
        # Tracebacks may double their backslashes; normalize only for matching.
        pattern = re.escape(root.replace("\\", "/")).replace("/", r"[\\/]+")
        text = re.sub(pattern, "<local>", text, flags=re.IGNORECASE)

    # A report may quote paths from another account or a previous machine.
    text = re.sub(r'(?<![\w])(?:[A-Za-z]:[\\/]+|\\\\)[^\r\n\'"`<>|]+', "<path>", text)
    text = re.sub(r'(?<![:/\w])/(?:home|Users|mnt|media|Volumes)/[^\r\n\'"`<>|]+', "<path>", text)
    user = os.environ.get("USERNAME", "")
    if user:
        text = re.sub(r"(?<![\w])" + re.escape(user) + r"(?![\w])", "<user>", text, flags=re.IGNORECASE)

    def public_url(match):
        try:
            parsed = urlsplit(match.group())
            host = parsed.hostname or ""
            try:
                ipaddress.ip_address(host)
                host = "<ip>"
            except ValueError:
                pass
            # Query strings and fragments can carry signed links or account tokens.
            return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
        except ValueError:
            return "<url>"

    text = re.sub(r'https?://[^\s<>`"\']+', public_url, text, flags=re.IGNORECASE)
    text = re.sub(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "<email>", text)
    text = re.sub(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", "<ip>", text)
    def public_ipv6(match):
        try:
            ipaddress.IPv6Address(match.group())
            return "<ip>"
        except ValueError:
            return match.group()
    text = re.sub(r"(?<![\w:])(?:[0-9A-Fa-f]{0,4}:){2,}[0-9A-Fa-f:.]*(?![\w:])", public_ipv6, text)
    text = re.sub(r"(?i)(authorization\s*:\s*bearer\s+|(?:api[_-]?key|(?:access[_-]?)?token|password|secret)\s*[=:]\s*)[^\s'\"<>]+", r"\1<redacted>", text)
    return text
