"""notify: email notification helpers shared by the personal projects.

    from notify import EmailConfig, send_email, log_alert, smtp_config

    cfg = smtp_config(prefix="/my-project/prod")   # env vars or SSM
    if cfg:
        send_email("Subject", "body text", EmailConfig(**cfg), html_body="<p>hi</p>")
    else:
        log_alert("Subject", "body text")          # SMTP not configured yet
"""

from __future__ import annotations

from .config import smtp_config
from .email import EmailConfig, log_alert, send_email

__all__ = ["EmailConfig", "send_email", "log_alert", "smtp_config"]

__version__ = "0.2.0"
