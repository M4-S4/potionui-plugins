from fastapi.testclient import TestClient

from src.plugin_api import AccountType, get_current_active_user

HEALTH_URL = "/api/plugins/video-producer/health"
HEALTH_DATA = {"status": "ok", "plugin": "video-producer", "version": "0.1.0"}


def test_health_answers_any_signed_in_user(client):
    response = client.get(HEALTH_URL)

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": HEALTH_DATA}


def test_health_answers_an_admin_the_same_way(app, client, make_user):
    app.dependency_overrides[get_current_active_user] = lambda: make_user(AccountType.ADMIN)

    assert client.get(HEALTH_URL).json() == {"success": True, "data": HEALTH_DATA}


def test_health_needs_a_signed_in_user(app):
    app.dependency_overrides.clear()

    with TestClient(app) as anonymous:
        assert anonymous.get(HEALTH_URL).status_code == 401
