from __future__ import annotations
import aws_cdk as cdk
from aws_cdk import (
    Stack,
    Tags,
    CfnOutput,
    RemovalPolicy,
    Duration,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_s3 as s3,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_events as events,
    aws_events_targets as targets,
    aws_secretsmanager as secretsmanager,
    aws_transfer as transfer,
)
from aws_cdk.custom_resources import (
    AwsCustomResource,
    AwsCustomResourcePolicy,
    AwsSdkCall,
    PhysicalResourceId,
)
from constructs import Construct


class NorthshireTrustStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        trust_cidr = self.node.try_get_context("trustCidr") or "10.10.0.0/16"
        platform_vpc_id = self.node.try_get_context("platformVpcId") or ""
        platform_cidr = self.node.try_get_context("platformCidr") or ""
        platform_account = self.node.try_get_context("platformAccountId") or ""
        peering_connection_id = self.node.try_get_context("peeringConnectionId") or ""

        peering_enabled = bool(platform_vpc_id and platform_cidr)

        # Default true - set to "false" (string) in cdk.json or via -c to skip the
        # $0.30/hour Transfer Family charge on sessions where SFTP isn't being tested.
        deploy_sftp_raw = self.node.try_get_context("deployTransferFamily")
        deploy_sftp = deploy_sftp_raw is None or str(deploy_sftp_raw).lower() != "false"

        Tags.of(self).add("Project", "access-iq")

        # ── VPC ───────────────────────────────────────────────────────────────
        # No NAT gateway: bastion lives in the public subnet (SSM connects outbound
        # via the IGW), so private subnets only need to talk to each other and to
        # peered VPCs - no internet egress required.
        vpc = ec2.Vpc(
            self,
            "TrustVpc",
            ip_addresses=ec2.IpAddresses.cidr(trust_cidr),
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=28,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        # ── Security Groups ───────────────────────────────────────────────────
        bastion_sg = ec2.SecurityGroup(
            self,
            "BastionSg",
            vpc=vpc,
            description="Northshire SSM bastion - no inbound, outbound via IGW",
            allow_all_outbound=True,
        )

        rds_sg = ec2.SecurityGroup(
            self,
            "RdsSg",
            vpc=vpc,
            description="Northshire Trust RDS Postgres",
            allow_all_outbound=False,
        )
        rds_sg.add_ingress_rule(
            peer=bastion_sg,
            connection=ec2.Port.tcp(5432),
            description="Bastion psql access",
        )
        if peering_enabled:
            rds_sg.add_ingress_rule(
                peer=ec2.Peer.ipv4(platform_cidr),
                connection=ec2.Port.tcp(5432),
                description="Platform ECS tasks via VPC peering",
            )

        sftp_sg = ec2.SecurityGroup(
            self,
            "SftpSg",
            vpc=vpc,
            description="Transfer Family SFTP",
            allow_all_outbound=False,
        )
        if peering_enabled:
            sftp_sg.add_ingress_rule(
                peer=ec2.Peer.ipv4(platform_cidr),
                connection=ec2.Port.tcp(22),
                description="Platform SFTP access via peering",
            )

        # ── VPC Peering Routes & DNS ─────────────────────────────────────────
        if peering_enabled and peering_connection_id:
            for i, subnet in enumerate(vpc.isolated_subnets):
                ec2.CfnRoute(
                    self,
                    f"PlatformRoute{i}",
                    route_table_id=subnet.route_table.route_table_id,
                    destination_cidr_block=platform_cidr,
                    vpc_peering_connection_id=peering_connection_id,
                )

            AwsCustomResource(
                self,
                "PeeringDnsAccepter",
                on_create=AwsSdkCall(
                    service="EC2",
                    action="modifyVpcPeeringConnectionOptions",
                    parameters={
                        "VpcPeeringConnectionId": peering_connection_id,
                        "AccepterPeeringConnectionOptions": {
                            "AllowDnsResolutionFromRemoteVpc": True,
                        },
                    },
                    physical_resource_id=PhysicalResourceId.of(
                        "peering-dns-accepter"
                    ),
                ),
                policy=AwsCustomResourcePolicy.from_sdk_calls(resources=["*"]),
                install_latest_aws_sdk=False,
            )

        # ── Secrets ───────────────────────────────────────────────────────────
        ehr_ro_secret = secretsmanager.Secret(
            self,
            "EhrRoSecret",
            secret_name="northshire/trust/rds/ehr-readonly",
            description="EHR mirror read-only user credentials for access-iq",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "ehr_ro_user"}',
                generate_string_key="password",
                exclude_punctuation=True,
            ),
        )

        urgent_ro_secret = secretsmanager.Secret(
            self,
            "UrgentRoSecret",
            secret_name="northshire/trust/rds/urgent-readonly",
            description="Urgent Care mirror read-only user credentials for access-iq",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "urgent_ro_user"}',
                generate_string_key="password",
                exclude_punctuation=True,
            ),
        )

        sftp_user_secret = secretsmanager.Secret(
            self,
            "SftpUserSecret",
            secret_name="northshire/trust/sftp/trust-sftp",
            description="SFTP user credentials for Transfer Family",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "trust_sftp"}',
                generate_string_key="password",
                exclude_punctuation=True,
            ),
        )

        # ── RDS Postgres ──────────────────────────────────────────────────────
        rds_subnet_group = rds.SubnetGroup(
            self,
            "RdsSubnetGroup",
            description="Trust RDS isolated subnet group",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )

        rds_param_group = rds.ParameterGroup(
            self,
            "RdsParamGroup",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16,
            ),
            parameters={"rds.force_ssl": "1"},
        )

        db_instance = rds.DatabaseInstance(
            self,
            "TrustRds",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T4G, ec2.InstanceSize.MICRO
            ),
            credentials=rds.Credentials.from_generated_secret(
                username="trust_admin",
                secret_name="northshire/trust/rds/admin",
            ),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            subnet_group=rds_subnet_group,
            security_groups=[rds_sg],
            multi_az=False,
            allocated_storage=20,
            max_allocated_storage=100,
            storage_type=rds.StorageType.GP3,
            deletion_protection=False,
            removal_policy=RemovalPolicy.DESTROY,
            backup_retention=cdk.Duration.days(1),
            delete_automated_backups=True,
            publicly_accessible=False,
            database_name="ehr",
            parameter_group=rds_param_group,
            storage_encrypted=True,
            cloudwatch_logs_exports=["postgresql"],
        )

        # ── SSM Bastion ───────────────────────────────────────────────────────
        # Public subnet + no inbound rules = secure SSM-only access.
        # The public IP is only used for outbound SSM agent traffic; nothing can
        # reach this instance inbound because the SG has no ingress rules.
        bastion_role = iam.Role(
            self,
            "BastionRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"), # type: ignore[arg-type]
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
            description="SSM-only bastion for Trust RDS debug access",
        )
        if db_instance.secret:
            db_instance.secret.grant_read(bastion_role)
        ehr_ro_secret.grant_read(bastion_role)
        urgent_ro_secret.grant_read(bastion_role)
        sftp_user_secret.grant_read(bastion_role)

        bastion_userdata = ec2.UserData.for_linux()
        bastion_userdata.add_commands("dnf install -y postgresql16")

        bastion = ec2.Instance(
            self,
            "Bastion",
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.T3, ec2.InstanceSize.NANO
            ),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_group=bastion_sg,
            role=bastion_role, # type: ignore[arg-type]
            require_imdsv2=True,
            user_data=bastion_userdata,
            # Public IP so SSM agent can reach SSM endpoints over the internet
            associate_public_ip_address=True,
        )

        # ── S3 Trust Exports Bucket ───────────────────────────────────────────
        trust_exports_bucket = s3.Bucket(
            self,
            "TrustExportsBucket",
            bucket_name=f"northshire-trust-exports-{self.account}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="expire-diagnostics-90d",
                    prefix="diagnostics/",
                    expiration=cdk.Duration.days(90),
                ),
                s3.LifecycleRule(
                    id="expire-providers-365d",
                    prefix="providers/",
                    expiration=cdk.Duration.days(365),
                ),
                s3.LifecycleRule(
                    id="expire-sftp-noncurrent",
                    prefix="sftp-incoming/",
                    noncurrent_version_expiration=cdk.Duration.days(30),
                ),
            ],
        )

        # IAM role publishing scripts assume to write to the bucket
        publisher_role = iam.Role(
            self,
            "NorthshirePublisherRole",
            role_name="NorthshireS3Publisher",
            assumed_by=iam.AccountPrincipal(self.account), # type: ignore[arg-type]
            description="Scoped role for northshire-hospital-sim publishing scripts",
        )
        trust_exports_bucket.grant_read_write(publisher_role)

        # Cross-account read access for Platform ECS ingestion tasks
        if platform_account:
            trust_exports_bucket.add_to_resource_policy(
                iam.PolicyStatement(
                    sid="PlatformCrossAccountRead",
                    actions=["s3:GetObject", "s3:ListBucket"],
                    resources=[
                        trust_exports_bucket.bucket_arn,
                        f"{trust_exports_bucket.bucket_arn}/*",
                    ],
                    principals=[iam.AccountPrincipal(platform_account)],
                )
            )

        # ── Transfer Family SFTP (optional) ───────────────────────────────────
        sftp_server = None
        if deploy_sftp:
            sftp_logging_role = iam.Role(
                self,
                "SftpLoggingRole",
                assumed_by=iam.ServicePrincipal("transfer.amazonaws.com"), # type: ignore[arg-type]
                managed_policies=[
                    iam.ManagedPolicy.from_aws_managed_policy_name(
                        "service-role/AWSTransferLoggingAccess"
                    )
                ],
                description="Transfer Family CloudWatch logging role",
            )

            sftp_s3_role = iam.Role(
                self,
                "SftpS3Role",
                assumed_by=iam.ServicePrincipal("transfer.amazonaws.com"), # type: ignore[arg-type]
                description="Transfer Family role to read/write Trust exports S3",
            )
            trust_exports_bucket.grant_read_write(sftp_s3_role)

            sftp_server = transfer.CfnServer(
                self,
                "SftpServer",
                protocols=["SFTP"],
                endpoint_type="VPC",
                endpoint_details=transfer.CfnServer.EndpointDetailsProperty(
                    vpc_id=vpc.vpc_id,
                    subnet_ids=[subnet.subnet_id for subnet in vpc.isolated_subnets],
                    security_group_ids=[sftp_sg.security_group_id],
                ),
                identity_provider_type="SERVICE_MANAGED",
                logging_role=sftp_logging_role.role_arn,
                tags=[cdk.CfnTag(key="Project", value="access-iq")],
            )

            sftp_user_role = iam.Role(
                self,
                "SftpUserRole",
                assumed_by=iam.ServicePrincipal("transfer.amazonaws.com"), # type: ignore[arg-type]
                description="Scoped role for trust_sftp user S3 access",
                inline_policies={
                    "sftp-user-s3": iam.PolicyDocument(
                        statements=[
                            iam.PolicyStatement(
                                actions=[
                                    "s3:PutObject",
                                    "s3:GetObject",
                                    "s3:DeleteObject",
                                    "s3:GetObjectVersion",
                                    "s3:DeleteObjectVersion",
                                ],
                                resources=[
                                    f"{trust_exports_bucket.bucket_arn}/sftp-incoming/*"
                                ],
                            ),
                            iam.PolicyStatement(
                                actions=["s3:ListBucket", "s3:GetBucketLocation"],
                                resources=[trust_exports_bucket.bucket_arn],
                            ),
                        ]
                    )
                },
            )

            transfer.CfnUser(
                self,
                "SftpTrustUser",
                server_id=sftp_server.attr_server_id,
                user_name="trust_sftp",
                role=sftp_user_role.role_arn,
                home_directory_type="LOGICAL",
                home_directory_mappings=[
                    transfer.CfnUser.HomeDirectoryMapEntryProperty(
                        entry="/outbound",
                        target=f"/{trust_exports_bucket.bucket_name}/sftp-incoming/outbound",
                    ),
                ],
                tags=[cdk.CfnTag(key="Project", value="access-iq")],
            )

        # ── Peering Accepter Role (for Platform account cross-account automation) ──
        if platform_account:
            peering_accepter_role = iam.Role(
                self,
                "PeeringAccepterRole",
                role_name="access-iq-peering-accepter",
                assumed_by=iam.AccountPrincipal(platform_account),
                description="Allows Platform account to manage VPC peering lifecycle",
                max_session_duration=cdk.Duration.hours(1),
            )
            peering_accepter_role.add_to_policy(
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "ec2:AcceptVpcPeeringConnection",
                        "ec2:CreateRoute",
                        "ec2:DeleteRoute",
                        "ec2:ModifyVpcPeeringConnectionOptions",
                    ],
                    resources=["*"],
                    conditions={
                        "StringEquals": {
                            "aws:RequestedRegion": self.region,
                        }
                    },
                )
            )

            CfnOutput(self, "PeeringAccepterRoleArn",
                value=peering_accepter_role.role_arn,
                export_name="NorthshireTrust-PeeringAccepterRoleArn",
                description="IAM role ARN for Platform cross-account peering automation",
            )

        # ── S3 Gateway Endpoint (Lambda in PRIVATE_ISOLATED needs this) ──────
        vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[
                ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)
            ],
        )

        # ── Simulation Lambda ─────────────────────────────────────────────────
        simulate_fn = _lambda.Function(
            self,
            "SimulateDailyDrop",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=_lambda.Code.from_asset("lambda/simulate_daily_drop"),
            timeout=Duration.minutes(5),
            memory_size=256,
            environment={
                "TRUST_BUCKET": trust_exports_bucket.bucket_name,
                "SFTP_PREFIX": "sftp-incoming/outbound/appointments",
                "DIAGNOSTICS_PREFIX": "diagnostics",
                "RDS_DSN": "",
            },
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[rds_sg],
        )

        trust_exports_bucket.grant_read_write(simulate_fn)

        # EventBridge rule — deployed DISABLED, enabled by session.sh after
        # Platform is ready
        simulation_rule = events.Rule(
            self,
            "SimulationSchedule",
            schedule=events.Schedule.rate(Duration.minutes(30)),
            enabled=False,
        )
        simulation_rule.add_target(targets.LambdaFunction(simulate_fn))

        # Outputs for session.sh
        CfnOutput(self, "SimulationRuleName",
            value=simulation_rule.rule_name,
            export_name="NorthshireTrust-SimulationRuleName",
            description="EventBridge rule name for simulation schedule",
        )
        CfnOutput(self, "SimulationLambdaName",
            value=simulate_fn.function_name,
            export_name="NorthshireTrust-SimulationLambdaName",
            description="Simulation Lambda function name",
        )

        # ── Outputs ───────────────────────────────────────────────────────────
        CfnOutput(self, "VpcId",
            value=vpc.vpc_id,
            export_name="NorthshireTrust-VpcId",
            description="Trust VPC ID",
        )
        CfnOutput(self, "IsolatedRouteTableIds",
            value=",".join(
                subnet.route_table.route_table_id
                for subnet in vpc.isolated_subnets
            ),
            export_name="NorthshireTrust-IsolatedRouteTableIds",
            description="Comma-separated isolated subnet route table IDs",
        )
        CfnOutput(self, "RdsEndpoint",
            value=db_instance.instance_endpoint.hostname,
            export_name="NorthshireTrust-RdsEndpoint",
            description="RDS Postgres endpoint hostname",
        )
        CfnOutput(self, "RdsPort",
            value=str(db_instance.instance_endpoint.port),
            export_name="NorthshireTrust-RdsPort",
            description="RDS Postgres port",
        )
        if db_instance.secret:
            CfnOutput(self, "RdsAdminSecretArn",
                value=db_instance.secret.secret_arn,
                export_name="NorthshireTrust-RdsAdminSecretArn",
                description="Secrets Manager ARN for RDS admin credentials",
            )
        CfnOutput(self, "EhrRoSecretArn",
            value=ehr_ro_secret.secret_arn,
            export_name="NorthshireTrust-EhrRoSecretArn",
            description="Secrets Manager ARN for EHR read-only user",
        )
        CfnOutput(self, "UrgentRoSecretArn",
            value=urgent_ro_secret.secret_arn,
            export_name="NorthshireTrust-UrgentRoSecretArn",
            description="Secrets Manager ARN for Urgent Care read-only user",
        )
        CfnOutput(self, "TrustExportsBucketName",
            value=trust_exports_bucket.bucket_name,
            export_name="NorthshireTrust-TrustExportsBucketName",
            description="S3 bucket for Trust diagnostics and provider exports",
        )
        CfnOutput(self, "PublisherRoleArn",
            value=publisher_role.role_arn,
            export_name="NorthshireTrust-PublisherRoleArn",
            description="IAM role ARN for northshire publishing scripts to assume",
        )
        CfnOutput(self, "BastionInstanceId",
            value=bastion.instance_id,
            export_name="NorthshireTrust-BastionInstanceId",
            description="SSM bastion EC2 instance ID",
        )
        if sftp_server:
            CfnOutput(self, "SftpServerId",
                value=sftp_server.attr_server_id,
                export_name="NorthshireTrust-SftpServerId",
                description="Transfer Family server ID",
            )
            CfnOutput(self, "SftpEndpoint",
                value=f"{sftp_server.attr_server_id}.server.transfer.{self.region}.amazonaws.com",
                export_name="NorthshireTrust-SftpEndpoint",
                description="SFTP server hostname (VPC-hosted, reachable via peering)",
            )
            CfnOutput(self, "SftpUserSecretArn",
                value=sftp_user_secret.secret_arn,
                export_name="NorthshireTrust-SftpUserSecretArn",
                description="SFTP user credentials",
            )
