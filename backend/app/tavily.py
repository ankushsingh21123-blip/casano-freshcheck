"""Tavily Search API client (credit-conscious, mock-testable).

Uses exactly one search per check: basic depth, max 5 results, no
generated answer — 1 credit per check on the free Researcher tier.
Only the fixed Tavily endpoint is ever contacted; no user-supplied
URLs are fetched. All HTTP has a 20-second timeout.

Tavily integration in this repo was tested against mocks only, not
against the live API (no API key was available during development).
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

from .config import TAVILY_API_URL, TAVILY_MAX_RESULTS, TAVILY_TIMEOUT_SECONDS
from .verdict import DATE_NOT_PROVIDED, evidence_date_from_snippet, parse_published_date

MAX_SNIPPET_LENGTH = 500


class TavilyError(Exception):
    """Honest Tavily failure: kind + human-readable detail, no faked verdict."""

    def __init__(self, kind: str, detail: str):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail


def is_valid_evidence_url(url: object) -> bool:
    """Evidence URLs must be http/https with a host. Anything else is dropped."""
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def build_evidence_item(result: dict) -> dict | None:
    """Normalise one raw Tavily result into a stored evidence citation.

    Returns None when the result has no valid http/https URL. The date is
    ``published_date`` when present and parseable, otherwise a date
    extracted from the snippet, otherwise None (displayed in the UI as
    "date not provided").
    """
    url = result.get("url", "")
    if not is_valid_evidence_url(url):
        return None
    title = str(result.get("title") or "Untitled result")
    snippet = str(result.get("content") or "")[:MAX_SNIPPET_LENGTH]

    parsed = parse_published_date(result.get("published_date"))
    date_source = "published_date"
    if parsed is None:
        parsed = evidence_date_from_snippet(snippet)
        date_source = "snippet_date" if parsed is not None else "not_provided"

    return {
        "title": title,
        "url": url,
        "date": parsed.isoformat() if parsed else None,
        "date_display": parsed.isoformat() if parsed else DATE_NOT_PROVIDED,
        "date_source": date_source,
        "snippet": snippet,
        "score": result.get("score"),
    }


def search_tavily(
    query: str,
    topic: str,
    api_key: str,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """Run one Tavily search and return normalised evidence items.

    Raises TavilyError on any failure (auth, rate limit, timeout,
    network, unexpected response) so callers can store an honest error
    state instead of inventing a verdict.
    """
    payload = {
        "query": query,
        "search_depth": "basic",
        "topic": topic,
        "max_results": TAVILY_MAX_RESULTS,
        "include_answer": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        with httpx.Client(timeout=TAVILY_TIMEOUT_SECONDS, transport=transport) as client:
            response = client.post(TAVILY_API_URL, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise TavilyError(
            "timeout",
            f"Tavily search timed out after {TAVILY_TIMEOUT_SECONDS:.0f} seconds.",
        ) from exc
    except httpx.RequestError as exc:
        raise TavilyError("network_error", f"Could not reach Tavily: {exc}.") from exc

    if response.status_code == 401:
        raise TavilyError(
            "authentication_failed",
            "Tavily rejected the API key (401). Check TAVILY_API_KEY.",
        )
    if response.status_code == 429:
        raise TavilyError(
            "rate_limited",
            "Tavily rate limit reached (429). Try again later.",
        )
    if response.status_code >= 400:
        raise TavilyError(
            "http_error",
            f"Tavily returned HTTP {response.status_code}.",
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise TavilyError(
            "invalid_response", "Tavily returned a response that was not JSON."
        ) from exc

    results = body.get("results")
    if not isinstance(results, list):
        raise TavilyError(
            "invalid_response", "Tavily response did not contain a results list."
        )

    evidence: list[dict] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        item = build_evidence_item(result)
        if item is not None:
            evidence.append(item)
    return evidence
