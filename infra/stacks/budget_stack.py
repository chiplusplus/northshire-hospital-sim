"""BudgetStack -- monthly cost ceiling with Lambda auto-teardown of Trust infrastructure."""

from __future__ import annotations

from typing import Any

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    Stack,
    aws_budgets as budgets,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
)
from constructs import Construct

_TEARDOWN_HANDLER = """\
import boto3
import json
import os
import urllib.request


def handler(event, context):
    stacks = os.environ["EPHEMERAL_STACKS"].split(",")
    region = os.environ["STACK_REGION"]
    alert_email = os.environ.get("ALERT_EMAIL")
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    alarm_topic_arn = os.environ.get("ALARM_TOPIC_ARN")

    message = (
        "Budget alarm triggered for Trust account. "
        f"Auto-destroying ephemeral stacks: {', '.join(stacks)}. "
        "Redeploy with `make up` when ready."
    )

    if alarm_topic_arn and alert_email:
        try:
            sns = boto3.client("sns", region_name=region)
            sns.publish(
                TopicArn=alarm_topic_arn,
                Subject="[TRUST] Budget auto-teardown started",
                Message=message,
            )
        except Exception as e:
            print(f"SNS notify failed: {e}")

    if slack_webhook_url:
        try:
            stack_list = "\\n".join(f"  • `{s}`" for s in stacks)
            blocks = [
                {"type": "header", "text": {"type": "plain_text", "text": ":rotating_light: Budget Auto-Teardown (Trust)"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": "*Trigger:* Monthly spend exceeded 80% of ceiling"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*Destroying ephemeral stacks:*\\n{stack_list}"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": "Redeploy with `make up` when ready."}},
            ]
            payload = json.dumps({"blocks": blocks, "text": message}).encode()
            req = urllib.request.Request(slack_webhook_url, data=payload, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"Slack notify failed: {e}")

    cf = boto3.client("cloudformation", region_name=region)
    for stack in stacks:
        try:
            cf.delete_stack(StackName=stack)
            print(f"Initiated destroy: {stack}")
        except Exception as e:
            print(f"Skip {stack}: {e}")
"""


class TrustBudgetStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        ephemeral_stack_names: list[str],
        ceiling_usd: int = 10,
        alert_email: str | None = None,
        slack_webhook_url: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        topic = sns.Topic(
            self,
            "BudgetAlarmTopic",
            topic_name="northshire-trust-budget-alarm",
        )

        topic.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[iam.ServicePrincipal("budgets.amazonaws.com")],
                actions=["sns:Publish"],
                resources=[topic.topic_arn],
            )
        )

        budgets.CfnBudget(
            self,
            "MonthlyCeiling",
            budget=budgets.CfnBudget.BudgetDataProperty(
                budget_type="COST",
                time_unit="MONTHLY",
                budget_limit=budgets.CfnBudget.SpendProperty(
                    amount=ceiling_usd,
                    unit="USD",
                ),
            ),
            notifications_with_subscribers=[
                budgets.CfnBudget.NotificationWithSubscribersProperty(
                    notification=budgets.CfnBudget.NotificationProperty(
                        notification_type="ACTUAL",
                        comparison_operator="GREATER_THAN",
                        threshold=80,
                        threshold_type="PERCENTAGE",
                    ),
                    subscribers=[
                        budgets.CfnBudget.SubscriberProperty(
                            subscription_type="SNS",
                            address=topic.topic_arn,
                        ),
                    ],
                ),
            ],
        )

        teardown_env: dict[str, str] = {
            "EPHEMERAL_STACKS": ",".join(ephemeral_stack_names),
            "STACK_REGION": cdk.Stack.of(self).region,
        }
        if alert_email:
            teardown_env["ALERT_EMAIL"] = alert_email
            teardown_env["ALARM_TOPIC_ARN"] = topic.topic_arn
        if slack_webhook_url:
            teardown_env["SLACK_WEBHOOK_URL"] = slack_webhook_url

        if alert_email:
            topic.add_subscription(subs.EmailSubscription(alert_email))

        teardown_fn = _lambda.Function(
            self,
            "TeardownFn",
            function_name="northshire-trust-budget-teardown",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.handler",
            code=_lambda.InlineCode(_TEARDOWN_HANDLER),
            timeout=Duration.minutes(5),
            environment=teardown_env,
        )

        teardown_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudformation:DeleteStack"],
                resources=[
                    f"arn:aws:cloudformation:{cdk.Stack.of(self).region}:{cdk.Stack.of(self).account}:stack/{name}/*"
                    for name in ephemeral_stack_names
                ],
            )
        )

        topic.grant_publish(teardown_fn)

        topic.add_subscription(subs.LambdaSubscription(teardown_fn))
