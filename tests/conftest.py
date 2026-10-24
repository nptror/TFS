import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"classes": ["10C2", "10C10", "12C9"]}', encoding="utf-8")
    monkeypatch.setattr(main, "CONFIG_PATH", config)
    with TestClient(app) as test_client:
        yield test_client
