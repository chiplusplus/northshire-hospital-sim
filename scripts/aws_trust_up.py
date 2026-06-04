#!/usr/bin/env python3
"""
One-command bootstrap for the Northshire Trust AWS environment.

Deploys the CDK stack, initialises RDS databases, generates synthetic data,
and publishes everything — leaving the environment ready for the Platform
ingestion flows to connect.

Usage:
    python3 scripts/aws_trust_up.py [options]
    make trust-init            # full stack including SFTP
    make trust-init-no-sftp    # skip Transfer Family ($0.30/hr saved)

Flags:
    --no-sftp         Skip Transfer Family deployment ($0.30/hr saved)
    --skip-deploy     Skip cdk deploy (stack already running)
    --skip-db-setup   Skip DB creation + schema init (re-use from a previous
                      session that has NOT been destroyed since)
    --skip-generate   Skip synthetic data generation (re-use data/staging/)
    --profile         AWS CLI profile (default: northshire-trust)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import boto3

REPO_ROOT    = Path(__file__).resolve().parents[1]
CDK_OUTPUTS  = REPO_ROOT / "infra" / "cdk-outputs.json"
STACK_NAME   = "NorthshireTrustStack"
TUNNEL_PID_FILE = REPO_ROOT / ".tunnel.pid"
TUNNEL_PORT  = 5433


# ── Output helpers ────────────────────────────────────────────────────────────

def step(msg: str) -> None:
    print(f"\n{'─' * 60}\n  {msg}\n{'─' * 60}")


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def run(cmd: list[str], **kwargs) -> None:
    """Run a subprocess, echoing the command first."""
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def require_tool(name: str, install_hint: str) -> str:
    path = shutil.which(name)
    if not path:
        sys.exit(f"ERROR: '{name}' not found.\n{install_hint}")
    return path


# ── CDK outputs ───────────────────────────────────────────────────────────────

def load_stack_outputs() -> dict:
    if not CDK_OUTPUTS.exists():
        sys.exit(
            f"ERROR: {CDK_OUTPUTS} not found.\n"
            "Run without --skip-deploy, or run: make cdk-deploy"
        )
    with CDK_OUTPUTS.open() as f:
        data = json.load(f)
    if STACK_NAME not in data:
        sys.exit(f"ERROR: '{STACK_NAME}' not in {CDK_OUTPUTS}. Available: {list(data)}")
    return data[STACK_NAME]


# ── SSM tunnel ────────────────────────────────────────────────────────────────

def wait_ssm_online(bastion_id: str, ssm_client, timeout: int = 300) -> None:
    print("  Waiting for SSM agent (up to 5 min) ...", end="", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = ssm_client.describe_instance_information(
            Filters=[{"Key": "InstanceIds", "Values": [bastion_id]}]
        )
        items = resp.get("InstanceInformationList", [])
        if items and items[0].get("PingStatus") == "Online":
            print(" online.")
            return
        print(".", end="", flush=True)
        time.sleep(15)
    print()
    sys.exit(f"ERROR: Bastion {bastion_id} did not register with SSM within {timeout}s.")


def start_tunnel(bastion_id: str, rds_endpoint: str, profile: str) -> int:
    """Start SSM port-forwarding as a detached background process. Returns PID."""
    params = json.dumps({
        "host": [rds_endpoint],
        "portNumber": ["5432"],
        "localPortNumber": [str(TUNNEL_PORT)],
    })
    proc = subprocess.Popen(
        ["aws", "ssm", "start-session",
         "--target", bastion_id,
         "--document-name", "AWS-StartPortForwardingSessionToRemoteHost",
         "--parameters", params,
         "--profile", profile],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,   # detach — survives after this script exits
    )
    TUNNEL_PID_FILE.write_text(str(proc.pid))
    return proc.pid


def wait_for_tunnel(timeout: int = 60) -> None:
    print(f"  Waiting for tunnel on localhost:{TUNNEL_PORT} ...", end="", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("localhost", TUNNEL_PORT), timeout=2):
                print(" ready.")
                return
        except OSError:
            print(".", end="", flush=True)
            time.sleep(3)
    print()
    sys.exit(f"ERROR: Tunnel did not open on localhost:{TUNNEL_PORT} within {timeout}s.")


# ── RDS setup ─────────────────────────────────────────────────────────────────

def psql(admin_pass: str, db: str, *, sql: str | None = None, file: Path | None = None) -> None:
    psql_bin = require_tool(
        "psql",
        "Install with: brew install libpq\n"
        "Then: echo 'export PATH=\"/opt/homebrew/opt/libpq/bin:$PATH\"' >> ~/.zshrc && source ~/.zshrc",
    )
    cmd = [psql_bin,
           "-h", "localhost", "-p", str(TUNNEL_PORT),
           "-U", "trust_admin", "-d", db,
           "-v", "ON_ERROR_STOP=1"]
    if sql:
        cmd += ["-c", sql]
    elif file:
        cmd += ["-f", str(file)]
    # Admin password goes via env var — safe regardless of special characters
    subprocess.run(cmd, env={**os.environ, "PGPASSWORD": admin_pass, "PGSSLMODE": "require"}, check=True, cwd=REPO_ROOT)


def db_exists(admin_pass: str, dbname: str) -> bool:
    psql = shutil.which("psql")
    if psql is None:
        raise RuntimeError("psql not found in PATH")

    result = subprocess.run(
        [
            psql,
            "-h", "localhost", "-p", str(TUNNEL_PORT),
            "-U", "trust_admin", "-d", "ehr",
            "-tAc", f"SELECT 1 FROM pg_database WHERE datname = '{dbname}'",
        ],
        env={**os.environ, "PGPASSWORD": admin_pass, "PGSSLMODE": "require"},
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() == "1"


def setup_databases(admin_pass: str, ehr_ro_pw: str, urgent_ro_pw: str) -> None:
    # Create the three databases CDK doesn't provision automatically
    for dbname in ("urgent_care", "ehr_mirror", "urgent_care_mirror"):
        if db_exists(admin_pass, dbname):
            ok(f"Database '{dbname}' already exists")
        else:
            psql(admin_pass, "ehr", sql=f"CREATE DATABASE {dbname}")
            ok(f"Created database '{dbname}'")

    # Apply schemas — all files use CREATE ... IF NOT EXISTS, safe to re-run
    psql(admin_pass, "ehr",                file=REPO_ROOT / "sql/ehr/init.sql")
    ok("Applied sql/ehr/init.sql")
    psql(admin_pass, "urgent_care",        file=REPO_ROOT / "sql/urgent_care/init.sql")
    ok("Applied sql/urgent_care/init.sql")
    psql(admin_pass, "ehr_mirror",         file=REPO_ROOT / "sql/ehr/init_mirror_readonly.sql")
    ok("Applied sql/ehr/init_mirror_readonly.sql")
    psql(admin_pass, "urgent_care_mirror", file=REPO_ROOT / "sql/urgent_care/init_mirror_readonly.sql")
    ok("Applied sql/urgent_care/init_mirror_readonly.sql")

    # The init SQL files create RO users with placeholder passwords; overwrite
    # them with the Secrets Manager values so sources.yaml and RDS stay in sync.
    # RO passwords are alphanumeric (exclude_punctuation=True), safe to inline.
    psql(admin_pass, "ehr", sql=f"ALTER ROLE ehr_ro_user WITH PASSWORD '{ehr_ro_pw}';")
    psql(admin_pass, "ehr", sql=f"ALTER ROLE urgent_ro_user WITH PASSWORD '{urgent_ro_pw}';")
    ok("Read-only user passwords synced from Secrets Manager")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    require_tool(
        "session-manager-plugin",
        "Install from:\n"
        "https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html",
    )

    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--no-sftp",       action="store_true", help="Skip Transfer Family (saves $0.30/hr)")
    p.add_argument("--skip-deploy",   action="store_true", help="Skip cdk deploy (stack already running)")
    p.add_argument("--skip-db-setup", action="store_true", help="Skip DB creation + schema init")
    p.add_argument("--skip-generate", action="store_true", help="Skip synthetic data generation")
    p.add_argument("--profile",       default="northshire-trust", help="AWS CLI profile")
    args = p.parse_args()

    # ── 1. CDK deploy ─────────────────────────────────────────────────────────
    if not args.skip_deploy:
        step("Deploying CDK stack")
        deploy_cmd = [
            "cdk", "deploy", "--all",
            "--outputs-file", "cdk-outputs.json",
            "--require-approval", "never",
        ]
        if args.no_sftp:
            deploy_cmd += ["-c", "deployTransferFamily=false"]
        run(deploy_cmd, cwd=REPO_ROOT / "infra")

    # ── 2. Generate sources.yaml (fetches real passwords from Secrets Manager) ─
    step("Generating sources.yaml")
    run([sys.executable, "scripts/export_outputs.py", "--profile", args.profile],
        cwd=REPO_ROOT)

    # ── 3. Load outputs + fetch secrets needed for DB setup ───────────────────
    outputs      = load_stack_outputs()
    bastion_id   = outputs["BastionInstanceId"]
    rds_endpoint = outputs["RdsEndpoint"]

    session = boto3.Session(profile_name=args.profile)
    sm = session.client("secretsmanager")

    def get_pw(arn_key: str, fallback: str) -> str:
        secret_id = outputs.get(arn_key) or fallback
        return json.loads(sm.get_secret_value(SecretId=secret_id)["SecretString"])["password"]

    admin_pw     = get_pw("RdsAdminSecretArn",  "northshire/trust/rds/admin")
    ehr_ro_pw    = get_pw("EhrRoSecretArn",     "northshire/trust/rds/ehr-readonly")
    urgent_ro_pw = get_pw("UrgentRoSecretArn",  "northshire/trust/rds/urgent-readonly")

    # ── 4. Wait for SSM bastion ────────────────────────────────────────────────
    step("Waiting for SSM bastion")
    wait_ssm_online(bastion_id, ssm_client=session.client("ssm"))

    # ── 5. Open SSM port-forwarding tunnel ────────────────────────────────────
    step(f"Opening SSM tunnel  localhost:{TUNNEL_PORT} → {rds_endpoint}:5432")
    tunnel_pid = start_tunnel(bastion_id, rds_endpoint, args.profile)
    wait_for_tunnel()
    ok(f"Tunnel running (PID {tunnel_pid}, written to {TUNNEL_PID_FILE.name})")

    # ── 6. Set up databases and schemas ───────────────────────────────────────
    if not args.skip_db_setup:
        step("Setting up databases and schemas")
        setup_databases(admin_pw, ehr_ro_pw, urgent_ro_pw)

    # ── 7. Generate synthetic data ────────────────────────────────────────────
    if not args.skip_generate:
        step("Generating synthetic data")
        run([sys.executable, "scripts/generate_data.py", "--staging-dir", "data/staging"],
            cwd=REPO_ROOT)

    # ── 8. Clear old Trust S3 data + publish fresh ─────────────────────────────
    step("Publishing data")
    sources = str(REPO_ROOT / "config/sources.yaml")
    staging  = str(REPO_ROOT / "data/staging")

    # Clear old exports so stale data doesn't linger
    trust_bucket = outputs.get("TrustExportsBucketName", "")
    if trust_bucket:
        s3_client = session.client("s3")
        for prefix in ["diagnostics/", "sftp-incoming/", "_simulation_queue/", "providers/"]:
            paginator = s3_client.get_paginator("list_objects_v2")
            keys = []
            for page in paginator.paginate(Bucket=trust_bucket, Prefix=prefix):
                keys.extend({"Key": obj["Key"]} for obj in page.get("Contents", []))
            if keys:
                for i in range(0, len(keys), 1000):
                    s3_client.delete_objects(Bucket=trust_bucket, Delete={"Objects": keys[i:i + 1000]})
                ok(f"Cleared s3://{trust_bucket}/{prefix} ({len(keys)} objects)")
            else:
                ok(f"s3://{trust_bucket}/{prefix} already empty")

    run([sys.executable, "scripts/publish_ehr.py",
         "--sources", sources, "--staging-core", f"{staging}/core"], cwd=REPO_ROOT)
    ok("EHR published")

    run([sys.executable, "scripts/publish_urgent_care.py",
         "--sources", sources, "--staging-core", f"{staging}/core"], cwd=REPO_ROOT)
    ok("Urgent care published")

    run([sys.executable, "scripts/publish_s3.py",
         "--sources", sources, "--staging-exports", f"{staging}/exports"], cwd=REPO_ROOT)
    ok("S3 exports published")

    sftp_deployed = bool(outputs.get("SftpEndpoint"))
    if sftp_deployed and not args.no_sftp:
        run([sys.executable, "scripts/publish_sftp.py",
             "--sources", sources, "--staging-exports", f"{staging}/exports"], cwd=REPO_ROOT)
        ok("SFTP exports published")

    run([sys.executable, "scripts/publish_simulation_queue.py",
         "--sources", sources, "--staging-dir", f"{staging}/simulation_queue"], cwd=REPO_ROOT)
    ok("Simulation queue published")

    # ── Done ───────────────────────────────────────────────────────────────────
    step("Trust environment ready")
    print(f"\n  RDS endpoint : {rds_endpoint}")
    print(f"  Tunnel       : localhost:{TUNNEL_PORT} → {rds_endpoint}:5432  (PID {tunnel_pid})")
    if sftp_deployed:
        print(f"  SFTP         : {outputs['SftpEndpoint']}")
    print(f"\n  Stop tunnel  : kill $(cat .tunnel.pid)")
    print(f"  Tear down    : make trust-down\n")


if __name__ == "__main__":
    main()
