import socket

import pytest

from potion_audit.client import ApiClient, ApiError, ApiUnreachable, unwrap

from conftest import PASSWORD, TOKEN, USER


def test_login_posts_the_form_fields_then_sends_the_bearer_token(fake_api):
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    me = unwrap(client.get_json("/api/auth/me"))
    method, path, body = fake_api.requests[0]
    assert (method, path) == ("POST", "/api/auth/login")
    assert body == f"username={USER}&password={PASSWORD}".encode()
    assert me["username"] == USER
    assert client.authenticated


def test_failed_login_raises_without_echoing_the_password(fake_api):
    client = ApiClient(fake_api.url)
    with pytest.raises(ApiError) as caught:
        client.login(USER, "wrong-password")
    assert caught.value.status == 401
    assert "wrong-password" not in str(caught.value)
    assert not client.authenticated


def test_get_json_returns_none_for_a_404_when_missing_is_allowed(fake_api):
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    assert client.get_json("/api/generations/G1/failure", missing_ok=True) is None


def test_get_json_raises_with_status_and_detail(fake_api):
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    with pytest.raises(ApiError) as caught:
        client.get_json("/api/does-not-exist")
    assert caught.value.status == 404
    assert "no fake route" in caught.value.detail


def test_download_streams_the_body_to_a_file_and_reads_its_name(fake_api, tmp_path):
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    result = client.download("/api/generations/history/G1/export-bundle", tmp_path / "sub" / "bundle.zip")
    assert result.path.read_bytes()[:2] == b"PK"
    assert result.size == result.path.stat().st_size
    assert result.filename == "bundle-G1.zip"
    assert not (tmp_path / "sub" / "bundle.zip.part").exists()


def test_a_closed_port_raises_api_unreachable():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    client = ApiClient(f"http://127.0.0.1:{port}", timeout=2)
    with pytest.raises(ApiUnreachable):
        client.login(USER, PASSWORD)


def test_unwrap_returns_data_of_an_envelope_and_raises_on_success_false():
    assert unwrap({"success": True, "data": [1], "message": None}) == [1]
    assert unwrap({"plain": True}) == {"plain": True}
    with pytest.raises(ValueError, match="nope"):
        unwrap({"success": False, "data": None, "message": "nope"})


def test_the_token_never_appears_in_an_api_error(fake_api):
    client = ApiClient(fake_api.url)
    client.login(USER, PASSWORD)
    with pytest.raises(ApiError) as caught:
        client.get_json("/api/does-not-exist")
    assert TOKEN not in str(caught.value)
