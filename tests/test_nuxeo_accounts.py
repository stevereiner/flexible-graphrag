"""Unit tests for which Nuxeo credentials an ingest or an auto sync uses (sources/nuxeo_accounts.py)."""
import pytest

from sources.nuxeo_accounts import backend_account, fill_missing, for_sync, server_key

pytestmark = pytest.mark.unit

BACKEND = "http://nuxeo:8080/nuxeo"


@pytest.fixture
def account(monkeypatch):
    for name in ("NUXEO_TOKEN", "NUXEO_SYNC_CREDENTIALS", "NUXEO_OAUTH2_ACCESS_TOKEN", "NUXEO_OAUTH2_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NUXEO_URL", BACKEND)
    monkeypatch.setenv("NUXEO_AUTH_METHOD", "basic")
    monkeypatch.setenv("NUXEO_USERNAME", "svc")
    monkeypatch.setenv("NUXEO_PASSWORD", "secret")
    return monkeypatch


def test_server_key_ignores_case_scheme_default_port_and_trailing_slash():
    assert server_key("http://Nuxeo:8080/nuxeo/") == server_key(BACKEND)
    assert server_key("http://nuxeo/nuxeo") == server_key("nuxeo:80/nuxeo")
    assert server_key("http://nuxeo2:8080/nuxeo") != server_key(BACKEND)


def test_backend_account_only_for_the_backends_server(account):
    assert backend_account(BACKEND)["username"] == "svc"
    assert backend_account("http://other:8080/nuxeo") is None
    account.delenv("NUXEO_PASSWORD")
    assert backend_account(BACKEND) is None  # no credentials configured: no account


def test_fill_missing_is_a_fallback(account):
    token = {"url": BACKEND, "path": "/x", "auth_method": "token", "token": "user-token"}
    assert fill_missing(token) == token  # the request's own credentials win
    bare = {"url": BACKEND, "path": "/x", "nodeIds": ["n1"]}
    filled = fill_missing(bare)
    assert (filled["username"], filled["password"], filled["nodeIds"]) == ("svc", "secret", ["n1"])
    other = {"url": "http://other:8080/nuxeo", "path": "/x"}
    assert fill_missing(other) == other  # no account on another server


def test_sync_credentials_follow_the_setting(account):
    token = {"url": BACKEND, "path": "/x", "auth_method": "token", "token": "user-token"}
    assert for_sync(token)["token"] == "user-token"  # default: token
    account.setenv("NUXEO_SYNC_CREDENTIALS", "account")
    synced = for_sync(token)
    assert (synced["auth_method"], synced["username"], "token" in synced) == ("basic", "svc", False)
    elsewhere = {**token, "url": "http://other:8080/nuxeo"}
    assert for_sync(elsewhere)["token"] == "user-token"  # the backend has no account there
