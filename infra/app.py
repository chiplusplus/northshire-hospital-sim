#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stacks.trust_stack import NorthshireTrustStack
from stacks.budget_stack import TrustBudgetStack

app = cdk.App()

cdk_env = cdk.Environment(
    account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
    region=app.node.try_get_context("trustRegion") or os.environ.get("CDK_DEFAULT_REGION"),
)

NorthshireTrustStack(
    app,
    "NorthshireTrustStack",
    env=cdk_env,
    description="Northshire NHS Trust simulated infrastructure (Project: access-iq)",
)

TrustBudgetStack(
    app,
    "TrustBudgetStack",
    ephemeral_stack_names=["NorthshireTrustStack"],
    ceiling_usd=10,
    alert_email=app.node.try_get_context("alertEmail"),
    slack_webhook_url=app.node.try_get_context("slackWebhookUrl"),
    env=cdk_env,
)

app.synth()
