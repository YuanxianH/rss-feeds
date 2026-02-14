"""Shared HTTP session factory with retries."""

from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def create_retry_session(
    *,
    user_agent: Optional[str] = None,
    accept: Optional[str] = None,
    retries: int = 2,
    backoff_factor: float = 0.5,
) -> requests.Session:
    """Create a requests session with retry policy for idempotent methods."""
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent or DEFAULT_USER_AGENT})
    if accept:
        session.headers.update({"Accept": accept})

    retry_policy = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        backoff_factor=backoff_factor,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry_policy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
