"""send_email / log_alert -- SMTP boundary mocked, nothing leaves the process."""

from __future__ import annotations

import logging

import pytest

from notify import EmailConfig, log_alert, send_email
from notify import email as email_mod


class _FakeSMTP:
    """Records what send_email does without opening a socket."""

    instances = []

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.started_tls = False
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.sent = msg


@pytest.fixture(autouse=True)
def _fake_smtp(monkeypatch):
    _FakeSMTP.instances = []
    monkeypatch.setattr(email_mod.smtplib, "SMTP", _FakeSMTP)
    yield


def _cfg(**kw):
    base = dict(
        smtp_host="smtp.gmail.com", smtp_port=587, username="me@x.com",
        password="pw", to_address="you@x.com",
    )
    base.update(kw)
    return EmailConfig(**base)


def test_from_address_defaults_to_username():
    assert _cfg().from_address == "me@x.com"
    assert _cfg(from_address="other@x.com").from_address == "other@x.com"


def test_send_email_starts_tls_logs_in_and_sends():
    send_email("Hi", "plain body", _cfg())
    smtp = _FakeSMTP.instances[-1]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 587)
    assert smtp.started_tls is True
    assert smtp.logged_in == ("me@x.com", "pw")
    assert smtp.sent["Subject"] == "Hi"
    assert smtp.sent["From"] == "me@x.com"
    assert smtp.sent["To"] == "you@x.com"
    assert smtp.sent.get_content().strip() == "plain body"


def test_send_email_attaches_html_alternative():
    send_email("Hi", "plain", _cfg(), html_body="<p>rich</p>")
    msg = _FakeSMTP.instances[-1].sent
    assert msg.is_multipart()
    subtypes = {p.get_content_subtype() for p in msg.iter_parts()}
    assert {"plain", "html"} <= subtypes


def test_send_email_propagates_smtp_errors(monkeypatch):
    class _Boom(_FakeSMTP):
        def login(self, user, password):
            raise RuntimeError("auth failed")

    monkeypatch.setattr(email_mod.smtplib, "SMTP", _Boom)
    with pytest.raises(RuntimeError, match="auth failed"):
        send_email("Hi", "body", _cfg())


def test_log_alert_warns(caplog):
    with caplog.at_level(logging.WARNING):
        log_alert("Subj", "body")
    assert any("SMTP not configured" in r.message for r in caplog.records)
