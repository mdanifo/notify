# notify

Shared email notification helpers for the personal projects
(`bronco-price-alerter`, `flight-price-alerter`, `virtual-closet`, …).

Before this, each project carried a byte-identical copy of an `EmailConfig` +
`send_email` + `log_alert` notifier and a near-identical env→SSM config
resolver. This is the single canonical version.

## Install

Pin it from git (no PyPI):

```bash
pip install "notify @ git+https://github.com/mdanifo/notify"
# with the SSM Parameter Store path:
pip install "notify[ssm] @ git+https://github.com/mdanifo/notify"
```

`boto3` is only needed for the SSM path — env-only callers can skip the `[ssm]`
extra entirely.

## Use

```python
from notify import EmailConfig, send_email, log_alert, smtp_config

cfg = smtp_config(prefix="/my-project/prod")   # env vars first, then SSM
if cfg:
    send_email("Subject", "plain body", EmailConfig(**cfg),
               html_body="<p>optional rich body</p>")
else:
    log_alert("Subject", "plain body")         # SMTP not configured yet -> logs
```

## Configuration

Every setting is read from an environment variable first, then from AWS SSM
Parameter Store under the `prefix` you pass (or the `PARAMETER_PREFIX` env var).
If no prefix is known, the SSM path is skipped — pure env config needs no AWS.

| Setting | Env var | SSM name (`<prefix>/…`) | Default |
|---|---|---|---|
| Username | `SMTP_USERNAME` | `smtp/username` | — (required) |
| Password | `SMTP_PASSWORD` | `smtp/password` | — (required) |
| Recipient | `ALERT_EMAIL_TO` | `alert-email/to` | — (required) |
| Sender | `ALERT_EMAIL_FROM` | `alert-email/from` | = username |
| Host | `SMTP_HOST` | `smtp/host` | `smtp.gmail.com` |
| Port | `SMTP_PORT` | `smtp/port` | `587` |

`smtp_config()` returns `None` unless username, password, and recipient all
resolve — so callers can cleanly fall back to `log_alert`. Secrets live as SSM
`SecureString` params set out-of-band; this library never writes them.

Use a Gmail **App Password** (not the account password):
https://support.google.com/accounts/answer/185833

## Develop

```bash
pip install -e ".[dev]"
pytest
```

## Roadmap

Tracked on the [Notify consolidation board](https://github.com/users/mdanifo/projects/4):
adopt in each project (delete the copies), consolidate the shared Gmail secret,
and optionally add a `push` (ntfy) backend so `nike-cleat-alerter` shares the
same package shape.
