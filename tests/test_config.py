"""smtp_config resolution: env-first, then SSM, with the SSM path fully mocked."""

from __future__ import annotations

import pytest

from notify import config as config_mod
from notify import smtp_config

# The env vars smtp_config reads; cleared before each test for isolation.
_ENV = [
    "SMTP_USERNAME", "SMTP_PASSWORD", "ALERT_EMAIL_TO", "ALERT_EMAIL_FROM",
    "SMTP_HOST", "SMTP_PORT", "PARAMETER_PREFIX", "SHARED_PARAMETER_PREFIX",
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


def test_an_empty_env_var_counts_as_unset(monkeypatch):
    """`SMTP_HOST=` left in a .env file must not shadow the SSM value with ''."""
    monkeypatch.setenv("SMTP_USERNAME", "me@x.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.setenv("ALERT_EMAIL_TO", "you@x.com")
    monkeypatch.setenv("SMTP_HOST", "")
    fake = _FakeSSM({"/proj/prod/smtp/host": "mail.example.com"})
    monkeypatch.setattr(config_mod, "_ssm", lambda: fake)
    assert smtp_config(prefix="/proj/prod")["smtp_host"] == "mail.example.com"


def test_port_from_the_environment_is_an_int(monkeypatch):
    monkeypatch.setenv("SMTP_USERNAME", "me@x.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.setenv("ALERT_EMAIL_TO", "you@x.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    assert smtp_config()["smtp_port"] == 465


def test_the_config_builds_an_email_config(monkeypatch):
    """The README does EmailConfig(**cfg), so the dict's keys are the
    dataclass's fields and nothing else."""
    from notify import EmailConfig

    monkeypatch.setenv("SMTP_USERNAME", "me@x.com")
    monkeypatch.setenv("SMTP_PASSWORD", "pw")
    monkeypatch.setenv("ALERT_EMAIL_TO", "you@x.com")
    cfg = EmailConfig(**smtp_config())
    assert (cfg.username, cfg.password, cfg.to_address) == ("me@x.com", "pw", "you@x.com")
    assert (cfg.from_address, cfg.smtp_host, cfg.smtp_port) == ("me@x.com", "smtp.gmail.com", 587)


def test_env_only_config_works_without_boto3_installed():
    """The [ssm] extra is optional: importing the package and resolving from
    the environment must not need boto3. Checked in a fresh interpreter with
    boto3 blocked."""
    import os
    import subprocess
    import sys

    code = "\n".join([
        "import sys",
        "sys.modules['boto3'] = None",
        "from notify import smtp_config",
        "print(smtp_config()['username'])",
    ])
    env = {k: v for k, v in os.environ.items() if k not in _ENV}
    env.update(SMTP_USERNAME="me@x.com", SMTP_PASSWORD="pw", ALERT_EMAIL_TO="you@x.com")
    result = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "me@x.com"


def test_the_ssm_client_is_built_once_for_the_configured_region(monkeypatch):
    import sys
    import types

    built = []

    def client(service, region_name=None):
        built.append((service, region_name))
        return object()

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client))
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    first = config_mod._ssm()
    assert config_mod._ssm() is first
    assert built == [("ssm", "us-east-1")]


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


# --- shared-credentials prefix ------------------------------------------------


def test_credentials_from_shared_recipient_from_project(monkeypatch):
    # The consolidation shape: creds live once under /shared, each project keeps
    # its own recipient under its own prefix.
    fake = _FakeSSM({
        "/shared/prod/smtp/username": "fleet@x.com",
        "/shared/prod/smtp/password": "shared-secret",
        "/proj/prod/alert-email/to": "proj-ops@x.com",
    })
    monkeypatch.setattr(config_mod, "_ssm", lambda: fake)

    cfg = smtp_config(prefix="/proj/prod", shared_prefix="/shared/prod")
    assert cfg["username"] == "fleet@x.com"
    assert cfg["password"] == "shared-secret"
    assert cfg["to_address"] == "proj-ops@x.com"       # per-project recipient
    assert cfg["from_address"] == "fleet@x.com"        # defaults to shared user


def test_shared_credentials_win_over_stale_project_copy(monkeypatch):
    # A leftover per-project credential must NOT shadow the shared one, so
    # rotating /shared is authoritative even before old copies are deleted.
    fake = _FakeSSM({
        "/shared/prod/smtp/username": "fleet@x.com",
        "/shared/prod/smtp/password": "new-shared-secret",
        "/proj/prod/smtp/username": "stale@x.com",
        "/proj/prod/smtp/password": "old-secret",
        "/proj/prod/alert-email/to": "ops@x.com",
    })
    monkeypatch.setattr(config_mod, "_ssm", lambda: fake)

    cfg = smtp_config(prefix="/proj/prod", shared_prefix="/shared/prod")
    assert cfg["username"] == "fleet@x.com"
    assert cfg["password"] == "new-shared-secret"


def test_shared_prefix_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("SHARED_PARAMETER_PREFIX", "/shared/prod")
    fake = _FakeSSM({
        "/shared/prod/smtp/username": "fleet@x.com",
        "/shared/prod/smtp/password": "secret",
        "/shared/prod/alert-email/to": "ops@x.com",  # falls back to shared when project lacks it
    })
    monkeypatch.setattr(config_mod, "_ssm", lambda: fake)
    cfg = smtp_config(prefix="/proj/prod")
    assert cfg["username"] == "fleet@x.com"
    assert cfg["to_address"] == "ops@x.com"


def test_host_port_and_sender_resolve_project_first(monkeypatch):
    """Only the credentials are shared-first. A project's own host, port and
    sender win over the shared ones, and the port comes back as an int."""
    fake = _FakeSSM({
        "/shared/prod/smtp/username": "fleet@x.com",
        "/shared/prod/smtp/password": "secret",
        "/shared/prod/smtp/host": "shared.example.com",
        "/shared/prod/smtp/port": "25",
        "/shared/prod/alert-email/from": "fleet@x.com",
        "/proj/prod/alert-email/to": "ops@x.com",
        "/proj/prod/alert-email/from": "proj@x.com",
        "/proj/prod/smtp/host": "proj.example.com",
        "/proj/prod/smtp/port": "2525",
    })
    monkeypatch.setattr(config_mod, "_ssm", lambda: fake)

    cfg = smtp_config(prefix="/proj/prod", shared_prefix="/shared/prod")
    assert cfg["smtp_host"] == "proj.example.com"
    assert cfg["smtp_port"] == 2525
    assert cfg["from_address"] == "proj@x.com"
