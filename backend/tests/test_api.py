"""API endpoint tests via TestClient. Tavily is monkeypatched, never live."""

import pytest

from app.tavily import TavilyError

QUESTION = "What is the electric vehicle battery range?"
ANSWER = "The electric vehicle battery range is 400 miles in 2024."


def test_health_reports_offline_without_key(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mode"] == "offline"
    assert body["service"] == "casano-freshcheck"


def test_health_reports_live_with_key_and_never_exposes_it(client, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-test-key")
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["mode"] == "live"
    assert "fake-test-key" not in response.text


def test_post_check_offline_returns_unknown_with_answer_only_analysis(client):
    response = client.post(
        "/checks",
        json={
            "question": QUESTION,
            "answer": "The range was 400 miles in 2023.",
            "answer_date": "2023-05-01",
            "topic": "news",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "offline"
    assert body["verdict"] == "UNKNOWN"
    assert body["evidence"] == []
    assert body["error"] is None
    assert body["signals"]["analysis_kind"] == "answer_only"
    assert body["signals"]["date_claims"]
    assert "TAVILY_API_KEY" in body["message"]
    assert body["topic"] == "news"
    assert body["answer_date"] == "2023-05-01"


def test_post_check_live_success_with_mocked_search(client, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-test-key")

    def fake_search(query, topic, api_key):
        assert topic == "general"
        return [
            {
                "title": "EV range report",
                "url": "https://example.com/ev",
                "date": "2024-06-15",
                "date_display": "2024-06-15",
                "date_source": "published_date",
                "snippet": (
                    "Electric vehicle battery range reaches 400 miles "
                    "in 2024 models."
                ),
                "score": 0.9,
            }
        ]

    monkeypatch.setattr("app.main.search_tavily", fake_search)
    response = client.post(
        "/checks",
        json={
            "question": QUESTION,
            "answer": ANSWER,
            "answer_date": "2024-06-01",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "live"
    assert body["verdict"] == "FRESH"
    assert len(body["evidence"]) == 1
    assert body["error"] is None
    assert body["reasons"]
    assert body["signals"]["evidence_count"] == 1


def test_post_check_live_tavily_error_returns_honest_error_state(client, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "fake-test-key")

    def failing_search(query, topic, api_key):
        raise TavilyError("rate_limited", "Tavily rate limit reached (429).")

    monkeypatch.setattr("app.main.search_tavily", failing_search)
    response = client.post(
        "/checks", json={"question": QUESTION, "answer": ANSWER}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "live"
    assert body["verdict"] == "UNKNOWN"
    assert body["error"]["kind"] == "rate_limited"
    assert body["evidence"] == []

    stored = client.get(f"/checks/{body['id']}")
    assert stored.status_code == 200
    assert stored.json()["error"]["kind"] == "rate_limited"


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "x" * 501, "answer": "ok"},
        {"question": "ok", "answer": "x" * 5001},
        {"question": "ok", "answer": "   "},
        {"question": "", "answer": "ok"},
        {"question": "ok", "answer": "ok", "topic": "finance"},
        {"question": "ok", "answer": "ok", "answer_date": "not-a-date"},
        {"question": "ok", "answer": "ok", "answer_date": "2024-13-40"},
    ],
)
def test_post_check_validation_errors(client, payload):
    response = client.post("/checks", json=payload)
    assert response.status_code == 422


def test_get_checks_lists_newest_first(client):
    first = client.post(
        "/checks", json={"question": "First question?", "answer": "First answer."}
    ).json()
    second = client.post(
        "/checks", json={"question": "Second question?", "answer": "Second answer."}
    ).json()
    response = client.get("/checks")
    assert response.status_code == 200
    checks = response.json()["checks"]
    assert [c["id"] for c in checks] == [second["id"], first["id"]]


def test_get_check_by_id_and_404(client):
    created = client.post(
        "/checks", json={"question": QUESTION, "answer": ANSWER}
    ).json()
    found = client.get(f"/checks/{created['id']}")
    assert found.status_code == 200
    assert found.json()["question"] == QUESTION
    assert client.get("/checks/999999").status_code == 404


def test_history_persists_across_clients(client, isolated_db, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    created = client.post(
        "/checks", json={"question": QUESTION, "answer": ANSWER}
    ).json()
    fresh_client = TestClient(app)
    found = fresh_client.get(f"/checks/{created['id']}")
    assert found.status_code == 200
    assert found.json()["answer"] == ANSWER


def test_root_reports_mode_without_key(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["mode"] == "offline"
    assert "Heuristic" in response.json()["note"]
