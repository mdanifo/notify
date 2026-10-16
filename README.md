# notify

Email notification helpers shared by the personal projects
(`bronco-price-alerter`, `flight-price-alerter`, `virtual-closet`): an
`EmailConfig`, `send_email`, `log_alert` as the no-credentials fallback, and
`smtp_config` to resolve the settings from environment variables or AWS SSM
Parameter Store.

## Install

There is no PyPI package. Install from git, pinned to a tag:

```bash
pip install "notify @ git+https://github.com/mdanifo/notify@v0.2.0"
# with the SSM Parameter Store path:
pip install "notify[ssm] @ git+https://github.com/mdanifo/notify@v0.2.0"
```

`boto3` is only needed for the SSM path. A caller configured from environment
variables can skip the `[ssm]` extra.

## Use

```python
from notify import EmailConfig, send_email, log_alert, smtp_config

# Per-project prefix for the recipient, shared prefix for the credentials.
cfg = smtp_config(prefix="/my-project/prod", shared_prefix="/shared/prod")
if cfg:
    send_email("Subject", "plain body", EmailConfig(**cfg),
               html_body="<p>optional rich body</p>")
else:
    log_alert("Subject", "plain body")  # SMTP not configured yet: log it instead
```

`send_email` raises whatever `smtplib` raises, so a bad SMTP setup fails the
job instead of dropping the message. `log_alert` logs at WARNING with the
subject and body as record fields.

## Configuration

Each setting is read from an environment variable first, then from SSM. An
empty environment variable counts as unset. Two SSM prefixes:

- `prefix` (or the `PARAMETER_PREFIX` env var): the per-project path, for
  example `/bronco-price-alerter/prod`.
- `shared_prefix` (or `SHARED_PARAMETER_PREFIX`): where the shared SMTP
  credentials live, for example `/shared/prod`.

Credentials resolve shared-first: rotating the Gmail App Password under
`/shared/prod` reaches every project, and a stale per-project copy is ignored.
Recipient, sender, host and port resolve project-first, which lets each project
say where its mail goes. A prefix left unset is skipped, and configuration from
environment variables alone needs no AWS.

| Setting   | Env var            | SSM name (under a prefix) | Default          |
|-----------|--------------------|---------------------------|------------------|
| Username  | `SMTP_USERNAME`    | `smtp/username`           | required         |
| Password  | `SMTP_PASSWORD`    | `smtp/password`           | required         |
| Recipient | `ALERT_EMAIL_TO`   | `alert-email/to`          | required         |
| Sender    | `ALERT_EMAIL_FROM` | `alert-email/from`        | the username     |
| Host      | `SMTP_HOST`        | `smtp/host`               | `smtp.gmail.com` |
| Port      | `SMTP_PORT`        | `smtp/port`               | `587`            |

`smtp_config()` returns `None` unless username, password and recipient all
resolve, which is the cue to fall back to `log_alert`. Secrets live as SSM
`SecureString` parameters set out of band; this library only reads them.

Use a Gmail App Password, not the account password:
https://support.google.com/accounts/answer/185833

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The suite fakes `smtplib.SMTP` and the SSM client; nothing leaves the process.
CI runs it on Python 3.9 and 3.12.

## Infrastructure

`infra/` holds two account-wide CloudFormation stacks, the shared alarms SNS
topic and the account CloudTrail; see [infra/README.md](infra/README.md). They
are not part of the Python package.
