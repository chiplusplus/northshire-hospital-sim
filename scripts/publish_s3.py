#!/usr/bin/env python3
from __future__ import annotations
import sys

import argparse
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml
import json

from northshire_sim.publishing.s3 import (
    S3Config,
    ensure_bucket_exists,
    make_s3_client,
    upload_file,
    upload_json_sidecar,
    cache_object, cache_bytes
)


def load_sources(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"sources.yaml not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Publish staged exports to Trust-owned S3 buckets.")
    p.add_argument("--sources", type=str, default="config/sources.yaml")
    p.add_argument("--staging-exports", type=str, default="data/staging/exports")
    p.add_argument("--create-buckets-if-missing", action="store_true", help="Best-effort create buckets (sim)")
    p.add_argument("--run-id", type=str, default=None, help="Optional run id for sidecars")
    p.add_argument("--cache-dir", type=str, default="data/s3_exports", help="Local cache of uploaded objects")
    p.add_argument("--no-cache", action="store_true", help="Disable local cache writes")

    return p.parse_args()


def main() -> None:
    args = parse_args()
    sources = load_sources(Path(args.sources))
    staging_exports = Path(args.staging_exports)

    s3_cfg_raw = sources.get("s3", {})
    region = s3_cfg_raw.get("region", "eu-west-2")
    endpoint_url = s3_cfg_raw.get("endpoint_url") 
    kms_key_id = s3_cfg_raw.get("kms_key_id")
    use_sse_s3 = bool(s3_cfg_raw.get("use_sse_s3", False))

    buckets = s3_cfg_raw.get("buckets", {})
    diagnostics_bucket = buckets.get("diagnostics")
    providers_bucket = buckets.get("providers")

    if not diagnostics_bucket or not providers_bucket:
        raise KeyError(
            "Missing bucket names in sources.yaml under:\n"
            "s3:\n"
            "  buckets:\n"
            "    diagnostics: ...\n"
            "    providers: ...\n"
        )

    prefixes = s3_cfg_raw.get("prefixes", {})
    diagnostics_prefix = prefixes.get("diagnostics", "exports/diagnostics")
    providers_prefix = prefixes.get("providers", "exports/providers")

    cfg = S3Config(
        region=region,
        endpoint_url=endpoint_url,
        kms_key_id=kms_key_id,
        use_sse_s3=use_sse_s3,
    )

    expected_account_id = s3_cfg_raw.get("expected_account_id")
    assume_role_arn = s3_cfg_raw.get("assume_role_arn")
    assume_role_session_name = s3_cfg_raw.get("assume_role_session_name")

    s3 = make_s3_client(
    cfg,
    expected_account_id=expected_account_id,
    assume_role_arn=assume_role_arn,
    assume_role_session_name=assume_role_session_name or "northshire-hospital-sim",
)

    if args.create_buckets_if_missing:
        ensure_bucket_exists(s3=s3, bucket=diagnostics_bucket, region=region)
        ensure_bucket_exists(s3=s3, bucket=providers_bucket, region=region)

    run_id = args.run_id or datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    # -------------------------
    # 1) Diagnostics daily exports
    # -------------------------
    diag_dir = staging_exports / "diagnostics"
    diag_files = sorted(diag_dir.glob("*_diagnostic_orders.csv"))

    uploaded_diag = 0
    for f in diag_files:
        # Expect filename like 2024-12-19_diagnostic_orders.csv
        date_str = f.name.split("_")[0]  # YYYY-MM-DD
        key = f"{diagnostics_prefix}/export_date={date_str}/{f.name}"

        upload_file(
            s3=s3,
            bucket=diagnostics_bucket,
            key=key,
            local_path=f,
            content_type="text/csv",
            cfg=cfg,
            extra_metadata={"source": "northshire_sim", "feed": "diagnostics_orders", "export_date": date_str},
        )

        # Sidecar
        sidecar_key = key.replace(".csv", ".metadata.json")
        sidecar_payload = {
            "run_id": run_id,
            "feed": "diagnostics_orders",
            "export_date": date_str,
            "filename": f.name,
            "generated_by": "northshire-hospital-sim",
        }
        upload_json_sidecar(
            s3=s3,
            bucket=diagnostics_bucket,
            key=sidecar_key,
            payload=sidecar_payload,
            cfg=cfg,
        )

        cache_root = Path(args.cache_dir)

        if not args.no_cache:
            cache_object(local_path=f, cache_root=cache_root, bucket=diagnostics_bucket, key=key)
            cache_bytes(
                payload_bytes=json.dumps(sidecar_payload, indent=2, default=str).encode("utf-8"),
                cache_root=cache_root,
                bucket=diagnostics_bucket,
                key=sidecar_key,
            )

        uploaded_diag += 1

    # -------------------------
    # 2) Provider reference Excel
    # -------------------------
    provider_xlsx = staging_exports / "providers" / "sites_and_services_master.xlsx"
    uploaded_providers = 0

    if provider_xlsx.exists():
        key = f"{providers_prefix}/{provider_xlsx.name}"

        upload_file(
            s3=s3,
            bucket=providers_bucket,
            key=key,
            local_path=provider_xlsx,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            cfg=cfg,
            extra_metadata={"source": "northshire_sim", "feed": "provider_reference"},
        )

        sidecar_key = key.replace(".xlsx", ".metadata.json")
        sidecar_payload = {
            "run_id": run_id,
            "feed": "provider_reference",
            "filename": provider_xlsx.name,
            "generated_by": "northshire-hospital-sim",
        }
        upload_json_sidecar(
            s3=s3,
            bucket=providers_bucket,
            key=sidecar_key,
            payload=sidecar_payload,
            cfg=cfg,
        )

        cache_root = Path(args.cache_dir)

        if not args.no_cache:
            cache_object(local_path=provider_xlsx, cache_root=cache_root, bucket=providers_bucket, key=key)
            cache_bytes(
                payload_bytes=json.dumps(sidecar_payload, indent=2, default=str).encode("utf-8"),
                cache_root=cache_root,
                bucket=providers_bucket,
                key=sidecar_key,
            )

        uploaded_providers = 1

    print("✅ Published to S3:")
    print(f"  diagnostics exports: {uploaded_diag} files → s3://{diagnostics_bucket}/{diagnostics_prefix}/...")
    print(f"  provider reference: {uploaded_providers} file → s3://{providers_bucket}/{providers_prefix}/...")


if __name__ == "__main__":
    main()
