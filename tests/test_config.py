"""smtp_config resolution: env-first, then SSM, with the SSM path fully mocked."""

from __future__ import annotations

import pytest

from notify import config as config_mod
from notify import smtp_config

# The env vars smtp_config reads; cleared before each test for isolation.
_ENV = [
    "SMTP_USERNAME", "SMTP_PASSWORD", "ALERT_EMAIL_TO", "ALERT_EMAIL_FROM",
    "SMTP_HOST", "SMTP_PORT", "PARAMETER_PREFIX",
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in _ENV:
        monkeypatch.delenv(k, raising=False)
    config_mod._ssm_client = None
    yield


def test_returns_none_when_nothing_configured():
    assert smtp_config() is None


def test_env_only_no_ssm_needed(monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "me@x.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.setenv("ALERT_EMAIL_TO", "you@x.com")

    # No prefix -> the SSM path must never be touched (would raise if it were).
    def _boom():
        raise AssertionError("SSM must not be used in env-only mode")

    monkeypatch.setattr(config_mod, "_ssm", _boom)

    cfg = smtp_config()
    assert cfg["username"] == "me@x.com"
    assert cfg["to_address"] == "you@x.com"
    assert cfg["from_address"] == "me@x.com"      # defaults to username
    assert cfg["smtp_host"] == "smtp.gmail.com"    # code default
    assert cfg["smtp_port"] == 587


def test_missing_required_value_returns_none(monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "me@x.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    # ALERT_EMAIL_TO absent -> incomplete -> None
    assert smtp_config() is None


class _FakeSSM:
    def __init__(self, store):
        self.store = store

    def get_parameter(self, Name, WithDecryption=False):
        if Name not in self.store:
            raise KeyError(Name)
        return {"Parameter": {"Value": self.store[Name]}}


def test_reads_from_ssm_under_prefix(monkeypatch):
    fake = _FakeSSM({
        "/proj/prod/smtp/username": "svc@x.com",
        "/proj/prod/smtp/password": "secret",
        "/proj/prod/alert-email/to": "ops@x.com",
    })
    monkeypatch.setattr(config_mod, "_ssm", lambda: fake)

    cfg = smtp_config(prefix="/proj/prod")
    assert cfg["username"] == "svc@x.com"
    assert cfg["password"] == "secret"
    assert cfg["to_address"] == "ops@x.com"


def test_prefix_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("PARAMETER_PREFIX", "/proj/prod")
    fake = _FakeSSM({
        "/proj/prod/smtp/username": "svc@x.com",
        "/proj/prod/smtp/password": "secret",
        "/proj/prod/alert-email/to": "ops@x.com",
    })
    monkeypatch.setattr(config_mod, "_ssm", lambda: fake)
    assert smtp_config()["username"] == "svc@x.com"


def test_env_wins_over_ssm(monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "env@x.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.setenv("ALERT_EMAIL_TO", "you@x.com")
    fake = _FakeSSM({"/proj/prod/smtp/username": "ssm@x.com"})
    monkeypatch.setattr(config_mod, "_ssm", lambda: fake)
    assert smtp_config(prefix="/proj/prod")["username"] == "env@x.com"
