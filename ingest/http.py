"""Shared HTTP helper for the keyed APIs.

Both OpenWeather and Agromonitoring take the key as a query parameter (appid). That would leak
the key into any exception message or log that shows the URL, so every error is redacted and
raised without chaining the original exception.
"""
import re
import time

import requests

HINTS = {
    401: "key rejected, not yet active, or mistyped",
    403: "key is valid but this endpoint is not included in the plan (entitlement)",
    404: "endpoint or resource not found",
    422: "request rejected as invalid (check parameters)",
    429: "rate limit or quota exceeded",
}


class ApiError(RuntimeError):
    def __init__(self, status, message, hint=""):
        self.status, self.hint = status, hint
        super().__init__(f"HTTP {status}: {message}" + (f" [{hint}]" if hint else ""))


def redact(text, secret=None):
    text = re.sub(r"(appid=)[^&\s'\"]+", r"\1***", str(text), flags=re.I)
    return text.replace(secret, "***") if secret else text


def call(method, url, *, secret, params=None, json_body=None, secret_param="appid",
         timeout=60, retries=3, sleep=None):
    """Returns (status, parsed_json). Raises ApiError (never containing the key)."""
    if not secret:
        raise ApiError(None, "credential is not set", "see docs/CREDENTIALS.md")
    query = dict(params or {})
    query[secret_param] = secret
    last = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.request(method, url, params=query, json=json_body, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as e:
            last = ApiError(None, redact(f"{type(e).__name__}: {e}", secret), "network problem or host not reachable")
        else:
            if r.status_code == 429 or r.status_code >= 500:
                last = ApiError(r.status_code, redact(r.text[:200], secret), HINTS.get(r.status_code, "server error"))
            elif r.status_code >= 400:
                raise ApiError(r.status_code, redact(r.text[:300], secret), HINTS.get(r.status_code, "")) from None
            else:
                try:
                    return r.status_code, r.json()
                except ValueError:
                    raise ApiError(r.status_code, "response was not JSON", "") from None
        if attempt < retries:
            (sleep or time.sleep)(2 ** attempt)
    raise last from None
