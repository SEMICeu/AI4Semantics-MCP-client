import os
import sys

from fastapi.testclient import TestClient


# Ensure project root is on sys.path so we can import app
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app  # noqa: E402


client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"


def test_chat_rejects_empty_message() -> None:
    response = client.post(
        "/chat",
        json={"user_name": "tester", "session_id": "session-1", "message": " "},
    )
    assert response.status_code == 400


def test_sessions_returns_list() -> None:
    response = client.get("/sessions", params={"user_name": "nonexistent_user_xyz"})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data == []
