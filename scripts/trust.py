from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List


def run(cmd: List[str]) -> None:
    print(f"\n$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="One command to bootstrap Northshire Trust simulated infrastructure + data.")
    p.add_argument("--sources", type=str, default="config/sources.yaml", help="Path to sources.yaml")
    p.add_argument("--staging-dir", type=str, default="data/staging", help="Where generate_data writes outputs")
    p.add_argument("--start-services", action="store_true", help="docker compose up -d before publishing")
    p.add_argument("--skip-generate", action="store_true", help="Skip data generation step")
    p.add_argument("--skip-ehr", action="store_true", help="Skip EHR internal + mirror publish")
    p.add_argument("--skip-urgent", action="store_true", help="Skip urgent care internal + mirror publish")
    p.add_argument("--skip-sftp", action="store_true", help="Skip SFTP publish")
    p.add_argument("--skip-s3", action="store_true", help="Skip S3 publish")
    p.add_argument("--skip-sim-queue", action="store_true", help="Skip simulation queue publish")
    p.add_argument("--create-buckets-if-missing", action="store_true", help="Best-effort bucket create (sim only)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    sources = str(repo_root / args.sources)

    if args.start_services:
        run(["docker", "compose", "up", "-d"])

    # 1) Generate staging outputs
    if not args.skip_generate:
        run(
            [
                sys.executable,
                "scripts/generate_data.py",
                "--staging-dir",
                args.staging_dir,
            ]
        )

    # 2) Publish EHR internal + refresh mirror
    if not args.skip_ehr:
        run(
            [
                sys.executable,
                "scripts/publish_ehr.py",
                "--sources",
                sources,
                "--staging-core",
                str(Path(args.staging_dir) / "core"),
            ]
        )

    # 3) Publish urgent care internal + refresh mirror
    if not args.skip_urgent:
        run(
            [
                sys.executable,
                "scripts/publish_urgent_care.py",
                "--sources",
                sources,
                "--staging-core",
                str(Path(args.staging_dir) / "core"),
            ]
        )

    # 4) Publish SFTP drops (appointments etc)
    if not args.skip_sftp:
        run(
            [
                sys.executable,
                "scripts/publish_sftp.py",
                "--staging-exports",
                str(Path(args.staging_dir) / "exports"),
            ]
        )

    # 5) Publish S3 (diagnostics + provider excel)
    if not args.skip_s3:
        cmd = [
            sys.executable,
            "scripts/publish_s3.py",
            "--sources",
            sources,
            "--staging-exports",
            str(Path(args.staging_dir) / "exports"),
        ]
        if args.create_buckets_if_missing:
            cmd.append("--create-buckets-if-missing")
        run(cmd)

    # 6) Publish simulation queue CSVs to S3
    if not args.skip_sim_queue:
        run(
            [
                sys.executable,
                "scripts/publish_simulation_queue.py",
                "--sources",
                sources,
                "--staging-dir",
                str(Path(args.staging_dir) / "simulation_queue"),
            ]
        )

    print("\n✅ Trust simulator bootstrap complete.")


if __name__ == "__main__":
    main()
