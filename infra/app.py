#!/usr/bin/env python3
import os
import aws_cdk as cdk
from stacks.trust_stack import NorthshireTrustStack

app = cdk.App()

NorthshireTrustStack(
    app,
    "NorthshireTrustStack",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=app.node.try_get_context("trustRegion") or os.environ.get("CDK_DEFAULT_REGION"),
    ),
    description="Northshire NHS Trust simulated infrastructure (Project: access-iq)",
)

app.synth()
