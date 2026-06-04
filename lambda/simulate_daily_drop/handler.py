"""Lambda: release the next day from the simulation queue.

Reads the earliest day=YYYY-MM-DD folder from _simulation_queue/,
publishes each file to its destination, then deletes the consumed folder.

TODO (production hardening): RDS credentials are currently passed via
environment variables. Move to Secrets Manager retrieval once VPC
endpoint connectivity is resolved.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
from typing import Any

import boto3
import psycopg2

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DAY_PATTERN = re.compile(r"day=(\d{4}-\d{2}-\d{2})/")


def _build_rds_dsn() -> str:
    """Build DSN from environment variables."""
    host = os.environ.get("RDS_HOST", "")
    port = os.environ.get("RDS_PORT", "5432")
    user = os.environ.get("RDS_USER", "")
    password = os.environ.get("RDS_PASSWORD", "")
    dbname = os.environ.get("RDS_DBNAME", "ehr")

    if not host or not user:
        return ""

    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}"


def handler(event: dict, context: Any) -> dict:
    trust_bucket = event.get("trust_bucket") or os.environ["TRUST_BUCKET"]
    queue_prefix = event.get("queue_prefix", "_simulation_queue")
    sftp_prefix = event.get("sftp_prefix") or os.environ.get("SFTP_PREFIX", "sftp-incoming/outbound/appointments")
    diagnostics_prefix = event.get("diagnostics_prefix") or os.environ.get("DIAGNOSTICS_PREFIX", "diagnostics")
    rds_dsn = event.get("rds_dsn") or _build_rds_dsn()

    logger.info("Handler start: bucket=%s, rds_dsn=%s", trust_bucket, "set" if rds_dsn else "empty")

    s3 = boto3.client("s3")
    logger.info("S3 client created, listing queue...")

    # 1. List all objects in the queue
    resp = s3.list_objects_v2(Bucket=trust_bucket, Prefix=f"{queue_prefix}/day=")
    if resp.get("KeyCount", 0) == 0:
        logger.info("Simulation queue empty — no-op")
        return {"status": "noop", "reason": "simulation queue empty"}

    # 2. Extract unique days, pick earliest
    days = set()
    for obj in resp.get("Contents", []):
        match = DAY_PATTERN.search(obj["Key"])
        if match:
            days.add(match.group(1))

    if not days:
        return {"status": "noop", "reason": "no day folders found"}

    target_day = sorted(days)[0]
    day_prefix = f"{queue_prefix}/day={target_day}/"
    logger.info("Publishing simulation day: %s", target_day)

    # 3. List files in the target day folder
    day_resp = s3.list_objects_v2(Bucket=trust_bucket, Prefix=day_prefix)
    day_files = {
        obj["Key"].split("/")[-1]: obj["Key"]
        for obj in day_resp.get("Contents", [])
    }

    # 4. Publish each file to its destination
    date_nodash = target_day.replace("-", "")

    if "appointments.csv" in day_files:
        _publish_appointments(s3, trust_bucket, day_files["appointments.csv"], sftp_prefix, date_nodash)

    for ehr_file in ["encounters.csv", "referrals.csv", "diagnoses.csv"]:
        if ehr_file in day_files:
            _publish_to_rds(s3, trust_bucket, day_files[ehr_file], rds_dsn, "ehr")

    if "urgent_care_logs.csv" in day_files:
        uc_dsn = rds_dsn.rsplit("/", 1)[0] + "/urgent_care" if rds_dsn else ""
        _publish_to_rds(s3, trust_bucket, day_files["urgent_care_logs.csv"], uc_dsn, "urgent_care")

    if "diagnostic_orders.csv" in day_files:
        _publish_diagnostics(s3, trust_bucket, day_files["diagnostic_orders.csv"], diagnostics_prefix, date_nodash)

    # 5. Delete consumed folder
    keys_to_delete = [{"Key": obj["Key"]} for obj in day_resp.get("Contents", [])]
    if keys_to_delete:
        s3.delete_objects(Bucket=trust_bucket, Delete={"Objects": keys_to_delete})

    logger.info("Day %s published and cleaned up", target_day)
    return {"status": "published", "day": target_day, "files": list(day_files.keys())}


def _publish_appointments(s3, bucket: str, source_key: str, sftp_prefix: str, date_nodash: str) -> None:
    dest_key = f"{sftp_prefix}/{date_nodash}_appointments.csv"
    s3.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": source_key},
        Key=dest_key,
    )
    logger.info("Appointments → %s", dest_key)


def _publish_diagnostics(s3, bucket: str, source_key: str, diagnostics_prefix: str, date_nodash: str) -> None:
    dest_key = f"{diagnostics_prefix}/export_date={date_nodash}/{date_nodash}_diagnostic_orders.csv"
    s3.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": source_key},
        Key=dest_key,
    )
    logger.info("Diagnostics → %s", dest_key)


def _publish_to_rds(s3, bucket: str, source_key: str, rds_dsn: str, db_name: str) -> None:
    if not rds_dsn:
        logger.warning("No RDS DSN available — skipping %s insert", db_name)
        return

    resp = s3.get_object(Bucket=bucket, Key=source_key)
    csv_body = resp["Body"].read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(csv_body))
    rows = list(reader)

    if not rows:
        return

    conn = psycopg2.connect(rds_dsn)
    try:
        cursor = conn.cursor()
        table = source_key.split("/")[-1].replace(".csv", "")
        columns = list(rows[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        col_names = ", ".join(f'"{c}"' for c in columns)

        insert_sql = f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})'

        for row in rows:
            cursor.execute(insert_sql, [row[c] for c in columns])

        conn.commit()
        logger.info("Inserted %d rows into %s.%s", len(rows), db_name, table)
    finally:
        conn.close()
