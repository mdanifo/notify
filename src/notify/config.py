"""Resolve SMTP settings from environment variables and/or AWS SSM.

Each setting is read from an environment variable first (which lets local runs
and tests work without touching AWS), then from AWS SSM Parameter Store. Two
prefixes are supported so a fleet of projects can share one set of credentials
while keeping their own recipient:

* ``shared_prefix`` -- where the shared SMTP **credentials** live (e.g.
  ``/shared/prod``). Rotating the Gmail App Password here updates every project.
* ``prefix`` -- the per-project path (e.g. ``/bronco-price-alerter/prod``),
  where a project's own ``alert-email/to`` / ``from`` overrides live.

Credentials resolve shared-first (so the shared value is authoritative); the
recipient resolves project-first (so a project can override where its mail
goes). The parameter names are stable everywhere -- ``smtp/username``,
``smtp/password``, ``alert-email/to``, ``alert-email/from``, ``smtp/host``,
``smtp/port``.

The SSM lookup is skipped for any prefix that is ``None``, so a purely
env-configured caller never needs AWS credentials or ``boto3`` installed.
Values are secrets; in AWS they live as ``SecureString`` parameters set
out-of-band -- nothing here ever writes them.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional, Sequence

logger = logging.getLogger(__name__)

_ssm_client = None


def _ssm():
    """Lazily create the SSM client so importing this module never requires AWS
    credentials (or boto3) -- only actually fetching a parameter does."""
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
    """Resolve one setting: environment variable first, then each prefix in
    order (first hit wins), then ``default``.

    ``None`` prefixes are skipped, so no-SSM callers need no AWS. A missing
    optional setting shouldn't crash the run, so a failed lookup falls through
    to the next prefix / the default rather than raising.
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
    """Assemble SMTP settings from env vars / Parameter Store.

    ``prefix`` is the per-project SSM path (falls back to the
    ``PARAMETER_PREFIX`` env var); ``shared_prefix`` is the shared-credentials
    path (falls back to ``SHARED_PARAMETER_PREFIX``). Credentials resolve
    shared-first, everything else project-first. Returns ``None`` when the
    required values (username, password, recipient) aren't available anywhere,
    so callers can fall back to :func:`notify.email.log_alert`.
    """
    prefix = prefix or os.getenv("PARAMETER_PREFIX")
    shared_prefix = shared_prefix or os.getenv("SHARED_PARAMETER_PREFIX")

    # Credentials: the shared value wins, so rotating it is authoritative and a
    # stale per-project copy is ignored. Recipient/host: project wins, so a
    # project can override where its mail goes.
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
