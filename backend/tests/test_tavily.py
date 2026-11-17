"""Tests for the Tavily client with MOCKED httpx transport only.

No live Tavily request is ever made in this suite.
"""

import json

import httpx
import pytest

from app.tavily import TavilyError, search_tavily


def _transport(handler):
    return httpx.MockTransport(handler)


def test_success_parses_results_with_published_date():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "query": "test",
                "results": [
                    {
                        "title": "Fresh News",
                        "url": "https://example.com/fresh",
                        "content": "Something happened recently.",
                        "score": 0.95,
                        "published_date": "2024-06-10",
                    }
                ],
            },
        )

    evidence = search_tavily(
        "test", "general", "fake-test-key", transport=_transport(handler)
    )
    assert captured["body"]["search_depth"] == "basic"
    assert captured["body"]["max_results"] == 5
    assert captured["body"]["include_answer"] is False
    assert captured["body"]["topic"] == "general"
    assert captured["auth"] == "Bearer fake-test-key"
    assert len(evidence) == 1
    assert evidence[0]["date"] == "2024-06-10"
    assert evidence[0]["date_source"] == "published_date"
    assert evidence[0]["title"] == "Fresh News"


def test_missing_published_date_falls_back_to_snippet_date():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "No date field",
                        "url": "https://example.com/nodate",
                        "content": "Reported in March 2024, the figures changed.",
                        "score": 0.8,
                    },
                    {
                        "title": "No date anywhere",
                        "url": "https://example.com/nodate2",
                        "content": "A timeless statement with no dates at all.",
                        "score": 0.7,
                    },
                ]
            },
        )

    evidence = search_tavily(
        "test", "news", "fake-test-key", transport=_transport(handler)
    )
    assert evidence[0]["date"] == "2024-03-01"
    assert evidence[0]["date_source"] == "snippet_date"
    assert evidence[1]["date"] is None
    assert evidence[1]["date_display"] == "date not provided"
    assert evidence[1]["date_source"] == "not_provided"


def test_401_raises_authentication_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "unauthorized"})

    with pytest.raises(TavilyError) as excinfo:
        search_tavily("test", "general", "fake-test-key", transport=_transport(handler))
    assert excinfo.value.kind == "authentication_failed"


def test_429_raises_rate_limited_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"detail": "slow down"})

    with pytest.raises(TavilyError) as excinfo:
        search_tavily("test", "general", "fake-test-key", transport=_transport(handler))
    assert excinfo.value.kind == "rate_limited"


def test_timeout_raises_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(TavilyError) as excinfo:
        search_tavily("test", "general", "fake-test-key", transport=_transport(handler))
    assert excinfo.value.kind == "timeout"


def test_network_error_raises_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure", request=request)

    with pytest.raises(TavilyError) as excinfo:
        search_tavily("test", "general", "fake-test-key", transport=_transport(handler))
    assert excinfo.value.kind == "network_error"


def test_invalid_evidence_urls_are_dropped():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"title": "Bad", "url": "ftp://example.com/x", "content": "x"},
                    {"title": "Worse", "url": "javascript:alert(1)", "content": "x"},
                    {"title": "No URL", "content": "x"},
                    {"title": "Good", "url": "https://example.com/ok", "content": "x"},
                ]
            },
        )

    evidence = search_tavily(
        "test", "general", "fake-test-key", transport=_transport(handler)
    )
    assert [item["title"] for item in evidence] == ["Good"]


def test_non_json_response_raises_invalid_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    with pytest.raises(TavilyError) as excinfo:
        search_tavily("test", "general", "fake-test-key", transport=_transport(handler))
    assert excinfo.value.kind == "invalid_response"
