"""Single place where outbound HTTP happens, so timeouts, User-Agent, retries and error classification are uniform
and tests can swap the transport (`client_factory`) without ever touching the network."""
from __future__ import annotations

import time
from typing import Callable

import httpx

from ..config import settings


class ExternalApiError(Exception):
    """A classified failure. `kind`: timeout | network | rate_limited | http_error | malformed | not_configured."""

    def __init__(self, kind: str, message: str, status: int | None = None, retry_after: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status = status
        self.retry_after = retry_after


def _default_factory() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        headers={"User-Agent": settings.http_user_agent, "Accept": "application/json, text/csv;q=0.9, */*;q=0.5"},
        follow_redirects=True,
    )


client_factory: Callable[[], httpx.Client] = _default_factory  # tests replace this


def request(method: str, url: str, *, params: dict | None = None, data: dict | None = None, auth=None,
            headers: dict | None = None, retries: int = 1, backoff: float = 0.6) -> httpx.Response:
    """Perform a request. Retries once on timeouts/5xx. Raises ExternalApiError (never returns an error response)."""
    last: ExternalApiError | None = None
    for attempt in range(retries + 1):
        try:
            with client_factory() as client:
                resp = client.request(method, url, params=params, data=data, auth=auth, headers=headers)
        except httpx.TimeoutException as exc:
            last = ExternalApiError("timeout", f"Timed out contacting {httpx.URL(url).host}")
            _ = exc
        except httpx.HTTPError as exc:
            last = ExternalApiError("network", f"Could not reach {httpx.URL(url).host}: {type(exc).__name__}")
        else:
            if resp.status_code == 429:
                ra = resp.headers.get("Retry-After", "")
                raise ExternalApiError("rate_limited", f"{httpx.URL(url).host} rate limit reached", 429, int(ra) if ra.isdigit() else None)
            if resp.status_code >= 500:
                last = ExternalApiError("http_error", f"{httpx.URL(url).host} returned HTTP {resp.status_code}", resp.status_code)
            elif resp.status_code >= 400:
                raise ExternalApiError("http_error", f"{httpx.URL(url).host} returned HTTP {resp.status_code}", resp.status_code)
            else:
                return resp
        if attempt < retries:
            time.sleep(backoff)
    assert last is not None
    raise last


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None, retries: int = 1) -> object:
    resp = request("GET", url, params=params, headers=headers, retries=retries)
    try:
        return resp.json()
    except ValueError as exc:  # e.g. USGS answers an unknown feed with HTTP 200 and a plain-text body
        raise ExternalApiError("malformed", "The response was not valid JSON", resp.status_code) from exc
