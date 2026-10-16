"""send_email and log_alert, with smtplib.SMTP faked; nothing leaves the process."""

from __future__ import annotations

import logging
import ssl

import pytest

from notify import EmailConfig, log_alert, send_email
from notify import email as email_mod


class _FakeSMTP:
    """Records what send_email does, and in what order, without opening a socket."""

    instances = []

    def __init__(self, host, port):
        self.host, self.port = host, port
        self.calls = []
        self.tls_context = None
        self.logged_in = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")
        self.tls_context = context

    def login(self, user, password):
        self.calls.append("login")
        self.logged_in = (user, password)

    def send_message(self, msg):
        self.calls.append("send_message")
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
    assert _cfg(from_address="").from_address == "me@x.com"
    assert _cfg(from_address="other@x.com").from_address == "other@x.com"


def test_send_email_starts_tls_before_logging_in_then_sends(caplog):
    """The password goes over the wire only after STARTTLS, with certificate
    verification on."""
    with caplog.at_level(logging.INFO):
        send_email("Hi", "plain body", _cfg())
    smtp = _FakeSMTP.instances[-1]
    assert (smtp.host, smtp.port) == ("smtp.gmail.com", 587)
    assert smtp.calls == ["starttls", "login", "send_message"]
    assert isinstance(smtp.tls_context, ssl.SSLContext)
    assert smtp.tls_context.verify_mode == ssl.CERT_REQUIRED
    assert smtp.logged_in == ("me@x.com", "pw")
    assert smtp.sent["Subject"] == "Hi"
    assert smtp.sent["From"] == "me@x.com"
    assert smtp.sent["To"] == "you@x.com"
    assert smtp.sent.get_content().strip() == "plain body"

    sent = [r for r in caplog.records if getattr(r, "event", None) == "email_sent"]
    assert len(sent) == 1 and sent[0].to == "you@x.com"


def test_send_email_attaches_html_alternative_and_keeps_the_plain_part():
    send_email("Hi", "plain", _cfg(), html_body="<p>rich</p>")
    msg = _FakeSMTP.instances[-1].sent
    assert msg.is_multipart()
    assert msg.get_body(preferencelist=("plain",)).get_content().strip() == "plain"
    assert msg.get_body(preferencelist=("html",)).get_content().strip() == "<p>rich</p>"


def test_send_email_propagates_smtp_errors(monkeypatch):
    class _Boom(_FakeSMTP):
        def login(self, user, password):
            raise RuntimeError("auth failed")

    monkeypatch.setattr(email_mod.smtplib, "SMTP", _Boom)
    with pytest.raises(RuntimeError, match="auth failed"):
        send_email("Hi", "body", _cfg())


def test_log_alert_warns_with_the_message_as_record_fields(caplog):
    """A log pipeline keys on `event` and reads the subject and body from the
    record, not from the message text."""
    with caplog.at_level(logging.WARNING):
        log_alert("Subj", "body")
    (record,) = [r for r in caplog.records if "SMTP not configured" in r.message]
    assert record.levelno == logging.WARNING
    assert (record.event, record.subject, record.body) == ("email_logged", "Subj", "body")
