"""Resolve SMTP settings from environment variables and AWS SSM.

Each setting is read from an environment variable first, then from SSM
Parameter Store. Two prefixes let a fleet of projects share one set of
credentials while keeping their own recipient:

* ``shared_prefix``: where the shared SMTP credentials live (e.g.
  ``/shared/prod``). Rotating the Gmail App Password there reaches every
  project.
* ``prefix``: the per-project path (e.g. ``/bronco-price-alerter/prod``),
  where a project's own ``alert-email/to`` and ``alert-email/from`` live.

Credentials resolve shared-first; recipient, sender, host and port resolve
project-first. The parameter names are the same under both prefixes:
``smtp/username``, ``smtp/password``, ``alert-email/to``, ``alert-email/from``,
``smtp/host``, ``smtp/port``.

A prefix that is ``None`` is skipped, so a caller configured from environment
variables alone needs neither AWS credentials nor ``boto3``. In AWS the values
are ``SecureString`` parameters set out of band; nothing here writes them.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional, Sequence

logger = logging.getLogger(__name__)

_ssm_client = None


def _ssm():
    """Create the SSM client on first use, so importing this module needs
    neither AWS credentials nor boto3."""
    global _ssm_client
    if _ssm_client is None:
        import boto3  # optional dependency; only needed for the SSM path

        _ssm_client = boto3.client("ssm", region_name=os.getenv("AWS_REGION"))
    return _ssm_client


def _get_setting(
    env_var: str,
    parameter_name: str,
    prefixes: Sequence[Optional[str]],
    default: Optional[str] = None,
) -> Optional[str]:
    """Resolve one setting: environment variable, then each prefix in order
    (first hit wins), then ``default``.

    ``None`` prefixes are skipped. A failed lookup falls through to the next
    prefix or the default instead of raising, so a missing optional setting
    cannot take the run down.
    """
    value = os.getenv(env_var)
    if value:
        return value

    for prefix in prefixes:
        if not prefix:
            continue
        try:
            response = _ssm().get_parameter(
                Name=f"{prefix}/{parameter_name}", WithDecryption=True
            )
            return response["Parameter"]["Value"]
        except Exception:
            continue

    logger.info(
        "Parameter not found, using default",
        extra={"event": "parameter_lookup_miss", "parameter": parameter_name},
    )
    return default


def smtp_config(
    prefix: Optional[str] = None, shared_prefix: Optional[str] = None
) -> Optional[Dict[str, object]]:
    """Assemble SMTP settings from environment variables and Parameter Store.

    ``prefix`` is the per-project SSM path (default: the ``PARAMETER_PREFIX``
    env var); ``shared_prefix`` is the shared-credentials path (default:
    ``SHARED_PARAMETER_PREFIX``). Credentials resolve shared-first, everything
    else project-first. Returns ``None`` when username, password or recipient
    is missing everywhere, so callers can fall back to
    :func:`notify.email.log_alert`.
    """
    prefix = prefix or os.getenv("PARAMETER_PREFIX")
    shared_prefix = shared_prefix or os.getenv("SHARED_PARAMETER_PREFIX")

    # Credentials: shared first, so a stale per-project copy is ignored.
    # Everything else: project first.
    cred_order = (shared_prefix, prefix)
    proj_order = (prefix, shared_prefix)

    username = _get_setting("SMTP_USERNAME", "smtp/username", cred_order)
    password = _get_setting("SMTP_PASSWORD", "smtp/password", cred_order)
    to_address = _get_setting("ALERT_EMAIL_TO", "alert-email/to", proj_order)
    if not (username and password and to_address):
        return None

    from_address = (
        _get_setting("ALERT_EMAIL_FROM", "alert-email/from", proj_order) or username
    )
    return {
        "smtp_host": _get_setting("SMTP_HOST", "smtp/host", proj_order, default="smtp.gmail.com"),
        "smtp_port": int(_get_setting("SMTP_PORT", "smtp/port", proj_order, default="587")),
        "username": username,
        "password": password,
        "to_address": to_address,
        "from_address": from_address,
    }
