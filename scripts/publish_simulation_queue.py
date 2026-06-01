#!/usr/bin/env python3
"""Upload simulation queue day-folders from local staging to Trust S3."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml

from northshire_sim.publishing.s3 import S3Config, make_s3_client


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Publish simulation queue to Trust S3.")
    p.add_argument("--sources", type=str, default="config/sources.yaml")
    p.add_argument("--staging-dir", type=str, default="data/staging/simulation_queue")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    sources_path = Path(args.sources)
    if not sources_path.exists():
        print("ERROR: sources.yaml not found")
        sys.exit(1)

    with sources_path.open("r") as f:
        sources = yaml.safe_load(f) or {}

    s3_cfg_raw = sources.get("s3", {})
    bucket = s3_cfg_raw.get("bucket")
    if not bucket:
        print("ERROR: No bucket in sources.yaml")
        sys.exit(1)

    cfg = S3Config(
        region=s3_cfg_raw.get("region", "eu-west-2"),
        endpoint_url=s3_cfg_raw.get("endpoint_url"),
        kms_key_id=s3_cfg_raw.get("kms_key_id"),
        use_sse_s3=bool(s3_cfg_raw.get("use_sse_s3", False)),
    )

    s3 = make_s3_client(
        cfg,
        expected_account_id=s3_cfg_raw.get("expected_account_id"),
        assume_role_arn=s3_cfg_raw.get("assume_role_arn"),
        assume_role_session_name=s3_cfg_raw.get("assume_role_session_name", "northshire-sim"),
    )

    staging_dir = Path(args.staging_dir)
    if not staging_dir.exists():
        print("No simulation queue to publish")
        return

    uploaded = 0
    for day_dir in sorted(staging_dir.iterdir()):
        if not day_dir.is_dir() or not day_dir.name.startswith("day="):
            continue
        for csv_file in day_dir.iterdir():
            if not csv_file.name.endswith(".csv"):
                continue
            key = f"_simulation_queue/{day_dir.name}/{csv_file.name}"
            s3.upload_file(str(csv_file), bucket, key)
            uploaded += 1

    print(f"✅ Published {uploaded} simulation queue files to s3://{bucket}/_simulation_queue/")


if __name__ == "__main__":
    main()
