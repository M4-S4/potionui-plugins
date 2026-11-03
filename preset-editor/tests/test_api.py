import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import router
from src.plugin_api import AccountType, User, get_current_active_user

ME_URL = "/api/plugins/preset-editor/me"


def _user(account_type):
    return User(
        id=f"{account_type.value.lower()}-1",
        username=account_type.value.lower(),
        email=f"{account_type.value.lower()}@test.com",
        password_hash="hash",
        account_type=account_type,
    )


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    yield app
    app.dependency_overrides.clear()


def test_me_answers_an_admin(app):
    app.dependency_overrides[get_current_active_user] = lambda: _user(AccountType.ADMIN)

    with TestClient(app) as client:
        response = client.get(ME_URL)

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"is_admin": True, "user_id": "admin-1", "plugin": "preset-editor", "version": "0.2.0"},
    }


def test_me_refuses_a_regular_user(app):
    app.dependency_overrides[get_current_active_user] = lambda: _user(AccountType.USER)

    with TestClient(app) as client:
        response = client.get(ME_URL)

    assert response.status_code == 403


def test_me_needs_a_signed_in_user(app):
    with TestClient(app) as client:
        response = client.get(ME_URL)

    assert response.status_code in (401, 403)
