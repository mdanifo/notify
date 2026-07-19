"""Resolve SMTP settings from environment variables and/or AWS SSM.

Each setting is read from an environment variable first (which lets local runs
and tests work without touching AWS) and from AWS SSM Parameter Store second,
under a ``prefix`` you supply (e.g. ``/bronco-price-alerter/prod`` or a shared
``/shared``). The parameter names are stable across all consumers --
``smtp/username``, ``smtp/password``, ``alert-email/to``, ``alert-email/from``,
``smtp/host``, ``smtp/port`` -- so one operational runbook applies everywhere.

The SSM lookup is skipped entirely when no prefix is known, so a purely
env-configured caller never needs AWS credentials or ``boto3`` installed.
Values are secrets; in AWS they live as ``SecureString`` parameters set
out-of-band -- nothing here ever writes them.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)

_ssm_client = None


def _resolve_prefix(prefix: Optional[str]) -> Optional[str]:
    """Explicit ``prefix`` wins; otherwise ``PARAMETER_PREFIX`` from the env.

    Resolved per call (not frozen at import) so env changes -- including test
    monkeypatching -- always take effect. Returns ``None`` when no prefix is
    configured, which turns off the SSM path (env-only mode).
    """
    return prefix or os.getenv("PARAMETER_PREFIX")


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
    *,
    prefix: Optional[str],
    default: Optional[str] = None,
) -> Optional[str]:
    """Resolve one setting: environment variable first, then Parameter Store.

    Returns ``default`` if neither source has a value, if no ``prefix`` is set,
    or if the Parameter Store lookup fails for any reason -- a missing optional
    setting shouldn't crash the whole run.
    """
    value = os.getenv(env_var)
    if value:
        return value

    if not prefix:
        return default

    try:
        response = _ssm().get_parameter(
            Name=f"{prefix}/{parameter_name}", WithDecryption=True
        )
        return response["Parameter"]["Value"]
    except Exception:
        logger.info(
            "Parameter not found, using default",
            extra={"event": "parameter_lookup_miss", "parameter": parameter_name},
        )
        return default


def smtp_config(prefix: Optional[str] = None) -> Optional[Dict[str, object]]:
    """Assemble SMTP settings from env vars / Parameter Store.

    ``prefix`` is the SSM path root (falls back to the ``PARAMETER_PREFIX`` env
    var). Returns ``None`` when the required values (username, password,
    recipient) aren't available anywhere, so callers can fall back to
    :func:`notify.email.log_alert`.
    """
    prefix = _resolve_prefix(prefix)
    username = _get_setting("SMTP_USERNAME", "smtp/username", prefix=prefix)
    password = _get_setting("SMTP_PASSWORD", "smtp/password", prefix=prefix)
    to_address = _get_setting("ALERT_EMAIL_TO", "alert-email/to", prefix=prefix)
    if not (username and password and to_address):
        return None

    from_address = (
        _get_setting("ALERT_EMAIL_FROM", "alert-email/from", prefix=prefix) or username
    )
    return {
        "smtp_host": _get_setting("SMTP_HOST", "smtp/host", prefix=prefix, default="smtp.gmail.com"),
        "smtp_port": int(_get_setting("SMTP_PORT", "smtp/port", prefix=prefix, default="587")),
        "username": username,
        "password": password,
        "to_address": to_address,
        "from_address": from_address,
    }
