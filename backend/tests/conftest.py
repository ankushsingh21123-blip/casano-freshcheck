"""Shared fixtures: isolated temp database, no Tavily key by default."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("FRESHCHECK_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    return tmp_path


@pytest.fixture()
def client(isolated_db):
    from app.main import app

    return TestClient(app)
