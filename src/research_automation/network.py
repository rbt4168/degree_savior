from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from .common import ResearchError


def public_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ResearchError("Downloads require a public HTTPS URL")
    try:
        destinations = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        raise ResearchError("Source hostname could not be resolved") from None
    for result in destinations:
        if not ipaddress.ip_address(result[4][0]).is_global:
            raise ResearchError("Private/local download destinations are not permitted")
    return url


class CheckedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch(url, *, limit=32 * 1024 * 1024, headers=None):
    public_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "ResearchAutomation/0.1 (bounded scholarly review)", **(headers or {})})
    opener = urllib.request.build_opener(CheckedRedirect())
    for attempt in range(3):
        try:
            with opener.open(request, timeout=25) as response:
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise ResearchError("Download exceeds configured size limit")
                return data
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise ResearchError(f"Source request failed: HTTP {error.code}") from None
            try:
                delay = float(error.headers.get("Retry-After", 2 ** attempt))
            except ValueError:
                delay = 2 ** attempt
            if delay > 30:
                raise ResearchError("Source rate-limited beyond this bounded request") from None
            time.sleep(max(0, delay))
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise ResearchError("Source connection failed or timed out") from None
            time.sleep(2 ** attempt)


def fetch_json(url, **kwargs):
    try:
        return json.loads(fetch(url, **kwargs))
    except (ValueError, UnicodeError):
        raise ResearchError("Source returned invalid JSON") from None
