"""Send notification emails over SMTP (e.g. Gmail with an App Password).

The shared version of the notifier that was copy-pasted across the personal
alerter projects (bronco/flight price alerters, virtual-closet daily digest):
an :class:`EmailConfig` + :func:`send_email`, plus :func:`log_alert` as a
no-credentials fallback used when SMTP isn't configured yet -- in a scheduled
Lambda/Fargate run that's the difference between "the message silently never
sent" and "it's visible in the logs even though email delivery isn't wired up
yet."

``send_email`` supports an optional HTML alternative so a digest can render as
a table in a mail client while still degrading to readable plain text.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EmailConfig:
    """Everything :func:`send_email` needs to deliver one message.

    ``from_address`` defaults to ``username`` when omitted -- most senders mail
    as themselves. Build one from :func:`notify.config.smtp_config` or by hand.
    """

    smtp_host: str
    smtp_port: int
    username: str
    password: str
    to_address: str
    from_address: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.from_address:
            self.from_address = self.username


def send_email(
    subject: str, body: str, config: EmailConfig, *, html_body: Optional[str] = None
) -> None:
    """Send an email notification.

    ``body`` is the plain-text content; pass ``html_body`` to attach an HTML
    alternative (the client picks the richest part it can render).

    Raises whatever smtplib raises on failure (auth error, connection error,
    etc.) -- callers deliberately don't catch this, so a bad SMTP config
    surfaces as a job error a monitor can catch, rather than a message that
    quietly never arrives.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.from_address
    msg["To"] = config.to_address
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
        server.starttls(context=context)
        server.login(config.username, config.password)
        server.send_message(msg)

    logger.info("Notification emailed", extra={"event": "email_sent", "to": config.to_address})


def log_alert(subject: str, body: str) -> None:
    """Fallback notifier used when no SMTP credentials are configured.

    Logs at WARNING (not INFO) so it stands out -- a message that only ever
    gets logged, never emailed, usually means the SMTP parameters haven't been
    set up yet.
    """
    logger.warning(
        "Notification not emailed (SMTP not configured) -- logging instead",
        extra={"event": "email_logged", "subject": subject, "body": body},
    )
