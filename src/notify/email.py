"""Send notification emails over SMTP (e.g. Gmail with an App Password).

:class:`EmailConfig` plus :func:`send_email`, and :func:`log_alert` as the
fallback for a scheduled run whose SMTP settings are not in place yet: the
message shows up in the logs instead of disappearing.

``send_email`` takes an optional HTML alternative, so a digest can render as a
table in a mail client and still read as plain text elsewhere.
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

    ``from_address`` defaults to ``username``. Build one from
    :func:`notify.config.smtp_config` or by hand.
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

    ``body`` is the plain-text content; ``html_body`` adds an HTML alternative,
    and the client picks the richest part it can render.

    Raises whatever smtplib raises (auth error, connection error), so a bad
    SMTP setup fails the job instead of dropping the message.
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
    """Fallback notifier for when no SMTP credentials are configured.

    Logs at WARNING, so a message that only ever gets logged stands out.
    """
    logger.warning(
        "Notification not emailed (SMTP not configured); logging instead",
        extra={"event": "email_logged", "subject": subject, "body": body},
    )
