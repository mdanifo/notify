# Shared account infrastructure

Account-wide CloudFormation stacks that belong to no single project. They live
here because `notify` was already the home of the first one; nothing in this
directory is part of the `notify` Python package.

| stack | template | owns |
|---|---|---|
| `shared-alarms` | `template.yaml` | the SNS topic every project's alarms fan into |
| `account-trail` | `account-trail.yaml` | the account-wide CloudTrail |

## shared-alarms

The infrastructure half of the notify consolidation (see notify#6). While the
`notify` **package** consolidates the notification *code* and the shared Gmail
secret lives out-of-band at `/shared/<stage>/smtp/*`, this stack consolidates
the operational-alarm *fan-in*: one SNS topic every project's CloudWatch alarms
publish run failures to, with a single email subscription — instead of a
per-project topic and a "Confirm subscription" click for each new project.

It owns only non-secret resources:

- `personal-alarms-<stage>` — the shared SNS topic.
- its email subscription (`OperatorEmail`).
- `/shared/<stage>/alarms-topic-arn` — an SSM `String` holding the topic ARN,
  the pointer projects read to find the topic.

The SMTP credentials stay out-of-band `SecureString`s (`notify` never writes
secrets), so they are not declared here.

## Deploy

```bash
aws cloudformation deploy \
  --template-file infra/template.yaml \
  --stack-name shared-alarms \
  --tags Project=notify \
  --parameter-overrides Stage=prod OperatorEmail=you@example.com \
  --region us-east-1 \
  --profile personal
```

After the first deploy, SNS emails a "Confirm subscription" link to
`OperatorEmail` — click it once. (No `--capabilities` needed; the stack creates
no IAM resources.)

## Consume from a project (SAM)

Each project's `template.yaml` reads the pointer and routes its alarms to the
shared topic, and no longer declares its own topic/subscription:

```yaml
Parameters:
  AlarmsTopicArn:
    Type: AWS::SSM::Parameter::Value<String>
    Default: /shared/prod/alarms-topic-arn

Resources:
  SomeAlarm:
    Type: AWS::CloudWatch::Alarm
    Properties:
      # ...
      AlarmActions:
        - !Ref AlarmsTopicArn
```

Deploy order matters: this `shared-alarms` stack must exist (so
`/shared/<stage>/alarms-topic-arn` resolves) before a consuming project deploys
the change. For Terraform consumers (virtual-closet), read the same SSM
parameter via a `data` source and use its value as the alarm action.


## account-trail

One multi-region CloudTrail writing **management events** to a private,
lifecycle-capped bucket. AWS keeps 90 days of Event history for free, which is
enough to diagnose something you already know about — it is not enough to
answer "when did this start" months later, and it cannot be archived or
searched offline.

Owns:

- `aws-cloudtrail-logs-<account>` — private, SSE-S3, versioned, all four public
  access blocks on, objects expiring after `RetentionDays` (default 365).
- the bucket policy CloudTrail writes through, with `aws:SourceArn` conditions
  as the confused-deputy guard.
- `account-trail` — multi-region, global service events, **log file validation
  on** so `aws cloudtrail validate-logs` can prove a file was not altered after
  delivery.

```bash
aws cloudformation deploy \
  --template-file infra/account-trail.yaml \
  --stack-name account-trail \
  --tags Project=notify \
  --region us-east-1 --profile personal
```

The bucket is `DeletionPolicy: Retain` — an audit log a stack delete can take
with it is not an audit log.

**Cost:** the first copy of management events is free; storage is a few tens of
megabytes a year, so this is cents per month. Data events (S3 object-level,
Lambda invokes) are deliberately **not** enabled — they are the expensive part
and nothing here needs them.
