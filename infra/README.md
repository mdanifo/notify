# Shared account infrastructure

Account-wide CloudFormation stacks that belong to no single project. They live
here because `notify` was the home of the first one. Nothing in this directory
is part of the `notify` Python package.

| stack | template | owns |
|---|---|---|
| `shared-alarms` | `template.yaml` | the SNS topic every project's alarms fan into |
| `account-trail` | `account-trail.yaml` | the account-wide CloudTrail |

## shared-alarms

One SNS topic that every project's CloudWatch alarms publish run failures to,
with a single email subscription, in place of a topic and a "Confirm
subscription" click per project. Non-secret resources only:

- `personal-alarms-<stage>`, the shared SNS topic
- its email subscription (`OperatorEmail`)
- `/shared/<stage>/alarms-topic-arn`, an SSM `String` holding the topic ARN,
  which is what projects read to find the topic

The SMTP credentials stay out-of-band `SecureString`s and are not declared
here.

### Deploy

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
`OperatorEmail`; click it once. No `--capabilities` flag is needed, as the
stack creates no IAM resources.

### Consume from a project (SAM)

A project's `template.yaml` reads the pointer and routes its alarms to the
shared topic instead of declaring its own topic and subscription:

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

Deploy `shared-alarms` first, so `/shared/<stage>/alarms-topic-arn` resolves
when the project deploys. A Terraform consumer (virtual-closet) reads the same
SSM parameter through a `data` source and uses its value as the alarm action.

## account-trail

One multi-region CloudTrail writing management events to a private,
lifecycle-capped bucket. AWS keeps 90 days of event history for free; this
keeps a year, searchable offline, for the "when did this start" question.

Owns:

- `aws-cloudtrail-logs-<account>`: private, SSE-S3, versioned, all four public
  access blocks on, objects expiring after `RetentionDays` (default 365)
- the bucket policy CloudTrail writes through, with `aws:SourceArn` conditions
  as the confused-deputy guard
- `account-trail`: multi-region, global service events, log file validation
  on, so `aws cloudtrail validate-logs` can prove a file was not altered after
  delivery

```bash
aws cloudformation deploy \
  --template-file infra/account-trail.yaml \
  --stack-name account-trail \
  --tags Project=notify \
  --region us-east-1 --profile personal
```

The bucket has `DeletionPolicy: Retain`, so deleting the stack keeps the log.

Cost: the first copy of management events is free and storage is a few tens of
megabytes a year, so cents per month. Data events (S3 object-level, Lambda
invokes) are not enabled; they are the expensive part and nothing here needs
them.
