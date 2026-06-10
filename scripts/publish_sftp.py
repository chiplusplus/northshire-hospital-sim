#!/usr/bin/env python3
"""Publish staged SFTP exports to the S3 prefix backing Transfer Family.

AWS Transfer Family maps the SFTP user's logical directory /outbound to
s3://<bucket>/sftp-incoming/outbound. This script uploads appointment CSVs
(and optionally other feeds) to that prefix so they're visible when the
Platform ingestion task connects via SFTP.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import boto3
import yaml


S3_SFTP_PREFIX = "sftp-incoming/outbound"


def load_sources(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"sources.yaml not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def upload_directory(
    s3,
    bucket: str,
    local_glob: str,
    s3_prefix: str,
) -> int:
    count = 0
    parent = Path(local_glob).parent
    pattern = Path(local_glob).name
    for f in sorted(parent.glob(pattern)):
        if not f.is_file():
            continue
        key = f"{s3_prefix}/{f.name}"
        s3.upload_file(str(f), bucket, key)
        count += 1
    return count


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Publish staged exports to the S3 prefix backing Transfer Family SFTP.",
    )
    p.add_argument(
        "--sources", type=str, default="config/sources.yaml",
        help="Path to sources.yaml (for S3 bucket/region config)",
    )
    p.add_argument(
        "--staging-exports", type=str, default="data/staging/exports",
        help="Exports staging dir",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    sources = load_sources(Path(args.sources))
    staging_exports = Path(args.staging_exports)

    s3_cfg = sources.get("s3", {})
    bucket = s3_cfg["bucket"]
    region = s3_cfg.get("region", "eu-west-2")
    profile = s3_cfg.get("profile")

    session = boto3.Session(profile_name=profile, region_name=region)
    s3 = session.client("s3")

    appt_n = upload_directory(
        s3, bucket,
        str(staging_exports / "appointments" / "*_appointments.csv"),
        f"{S3_SFTP_PREFIX}/appointments",
    )

    gp_n = 0
    if (staging_exports / "gp_registrations").exists():
        gp_n = upload_directory(
            s3, bucket,
            str(staging_exports / "gp_registrations" / "*_gp_registrations.csv"),
            f"{S3_SFTP_PREFIX}/gp_registrations",
        )

    esr_n = 0
    if (staging_exports / "esr").exists():
        esr_n = upload_directory(
            s3, bucket,
            str(staging_exports / "esr" / "*_esr_*.csv"),
            f"{S3_SFTP_PREFIX}/esr",
        )

    print(f"✅ Published to s3://{bucket}/{S3_SFTP_PREFIX}/:")
    print(f"  appointments: {appt_n} files")
    print(f"  gp_registrations: {gp_n} files")
    print(f"  esr: {esr_n} files")


if __name__ == "__main__":
    main()
