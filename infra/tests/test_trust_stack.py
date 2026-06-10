from __future__ import annotations
import aws_cdk as cdk
from aws_cdk import assertions
from stacks.trust_stack import NorthshireTrustStack

BASE_CONTEXT = {
    "trustCidr": "10.10.0.0/16",
    "platformVpcId": "vpc-abc123",
    "platformCidr": "10.20.0.0/16",
    "platformAccountId": "123456789012",
    "deployTransferFamily": "false",
}


def _synth(extra_context: dict | None = None) -> assertions.Template:
    app = cdk.App(context={**BASE_CONTEXT, **(extra_context or {})})
    stack = NorthshireTrustStack(
        app,
        "TestTrustStack",
        env=cdk.Environment(account="111111111111", region="eu-west-2"),
    )
    return assertions.Template.from_stack(stack)


class TestPeeringRoutes:
    def test_routes_created_when_peering_connection_provided(self):
        template = _synth({"peeringConnectionId": "pcx-abc123"})
        # 2 baseline public-subnet IGW routes + 2 peering routes
        template.resource_count_is("AWS::EC2::Route", 4)
        template.has_resource_properties(
            "AWS::EC2::Route",
            {
                "DestinationCidrBlock": "10.20.0.0/16",
                "VpcPeeringConnectionId": "pcx-abc123",
            },
        )

    def test_dns_accepter_created_when_peering_connection_provided(self):
        template = _synth({"peeringConnectionId": "pcx-abc123"})
        template.has_resource_properties(
            "Custom::AWS",
            assertions.Match.object_like(
                {
                    "Create": assertions.Match.serialized_json(
                        assertions.Match.object_like(
                            {
                                "service": "EC2",
                                "action": "modifyVpcPeeringConnectionOptions",
                                "parameters": {
                                    "VpcPeeringConnectionId": "pcx-abc123",
                                    "AccepterPeeringConnectionOptions": {
                                        "AllowDnsResolutionFromRemoteVpc": True,
                                    },
                                },
                            }
                        )
                    )
                }
            ),
        )

    def test_no_peering_routes_or_custom_resources_without_peering_connection(self):
        template = _synth()
        # Only the 2 baseline public-subnet IGW routes — no peering routes
        template.resource_count_is("AWS::EC2::Route", 2)
        template.resource_count_is("Custom::AWS", 0)
