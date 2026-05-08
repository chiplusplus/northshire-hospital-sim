#!/usr/bin/env python3
"""
Read CDK stack outputs from cdk-outputs.json, fetch secrets from
Secrets Manager, and write a ready-to-use config/sources.yaml.

Usage:
    python3 scripts/export_outputs.py \
        --cdk-outputs infra/cdk-outputs.json \
        --sources config/sources.yaml \
        [--profile northshire-trust]
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import quote_plus

import boto3
import yaml


STACK_NAME = "NorthshireTrustStack"


def load_outputs(cdk_outputs_path: Path) -> dict:
    if not cdk_outputs_path.exists():
        sys.exit(
            f"ERROR: {cdk_outputs_path} not found.\n"
            "Run:  cd infra && cdk deploy --outputs-file cdk-outputs.json"
        )
    with cdk_outputs_path.open() as f:
        all_outputs = json.load(f)
    if STACK_NAME not in all_outputs:
        sys.exit(
            f"ERROR: key '{STACK_NAME}' not found in {cdk_outputs_path}.\n"
            f"Available stacks: {list(all_outputs.keys())}"
        )
    return all_outputs[STACK_NAME]


def get_secret_password(sm_client, secret_id: str) -> str:
    """Fetch a secret from Secrets Manager and return the 'password' field."""
    resp = sm_client.get_secret_value(SecretId=secret_id)
    secret = json.loads(resp["SecretString"])
    return secret["password"]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cdk-outputs", default="infra/cdk-outputs.json", help="Path to cdk-outputs.json")
    p.add_argument("--sources", default="config/sources.yaml", help="Path to write sources.yaml")
    p.add_argument("--profile", default="northshire-trust", help="AWS CLI profile name")
    args = p.parse_args()

    outputs = load_outputs(Path(args.cdk_outputs))

    rds_endpoint = outputs["RdsEndpoint"]
    sftp_endpoint = outputs.get("SftpEndpoint", "")
    bucket_name = outputs["TrustExportsBucketName"]
    publisher_arn = outputs["PublisherRoleArn"]
    admin_secret_arn = outputs.get("RdsAdminSecretArn", "")
    ehr_ro_secret_arn = outputs.get("EhrRoSecretArn", "")
    urgent_ro_secret_arn = outputs.get("UrgentRoSecretArn", "")
    sftp_secret_arn = outputs.get("SftpUserSecretArn", "")

    # --- Fetch secrets from Secrets Manager ---
    session = boto3.Session(profile_name=args.profile)
    sm = session.client("secretsmanager")

    admin_pw = get_secret_password(sm, admin_secret_arn or "northshire/trust/rds/admin")
    ehr_ro_pw = get_secret_password(sm, ehr_ro_secret_arn or "northshire/trust/rds/ehr-readonly")
    urgent_ro_pw = get_secret_password(sm, urgent_ro_secret_arn or "northshire/trust/rds/urgent-readonly")
    sftp_pw = get_secret_password(sm, sftp_secret_arn or "northshire/trust/sftp/trust-sftp")

    sources = {
        "postgres": {
            "ehr_internal_dsn": f"postgresql+psycopg2://trust_admin:{quote_plus(admin_pw)}@localhost:5433/ehr",
            "urgent_internal_dsn": f"postgresql+psycopg2://trust_admin:{quote_plus(admin_pw)}@localhost:5433/urgent_care",
            "ehr_mirror_dsn": f"postgresql+psycopg2://trust_admin:{quote_plus(admin_pw)}@localhost:5433/ehr_mirror",
            "urgent_mirror_dsn": f"postgresql+psycopg2://trust_admin:{quote_plus(admin_pw)}@localhost:5433/urgent_care_mirror",
        },
        "sftp": {
            "host": sftp_endpoint or "NOT_DEPLOYED",
            "port": 22,
            "username": "trust_sftp",
            "password": sftp_pw,
            "outbound_root": "/outbound",
        },
        "s3": {
            "region": "eu-west-2",
            "profile": args.profile,
            "assume_role_arn": publisher_arn,
            "assume_role_session_name": "northshire-hospital-sim",
            "endpoint_url": None,
            "use_sse_s3": True,
            "kms_key_id": None,
            "bucket": bucket_name,
            "prefixes": {
                "diagnostics": "diagnostics",
                "providers": "providers",
            },
        },
    }

    out = Path(args.sources)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        yaml.dump(sources, f, default_flow_style=False, sort_keys=False)

    print(f"Written: {out}")
    print("WARNING: sources.yaml now contains real passwords.")
    print("Make sure it is in .gitignore and not committed to version control.")


if __name__ == "__main__":
    main()