from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import boto3
import shutil
from botocore.exceptions import ClientError


@dataclass(frozen=True)
class S3Config:
    region: str = "eu-west-2"  
    profile: Optional[str] = None  
    endpoint_url: Optional[str] = None  # e.g. for LocalStack
    kms_key_id: Optional[str] = None  # optional SSE-KMS
    use_sse_s3: bool = False  # SSE-S3 if True

def _get_account_id(session: boto3.Session) -> str:
    sts = session.client("sts")
    return sts.get_caller_identity()["Account"]

def _assume_role(session: boto3.Session, role_arn: str, session_name: str) -> boto3.Session:
    sts = session.client("sts")
    resp = sts.assume_role(RoleArn=role_arn, RoleSessionName=session_name)
    creds = resp["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )

def make_s3_client(cfg: S3Config, *, expected_account_id: str | None = None,
                   assume_role_arn: str | None = None, assume_role_session_name: str = "northshire-hospital-sim"):
    session_kwargs = {}
    if cfg.profile:
        session_kwargs["profile_name"] = cfg.profile

    base_session = boto3.Session(**session_kwargs)

    # Optional: assume role into target account
    session = base_session
    if assume_role_arn:
        session = _assume_role(base_session, assume_role_arn, assume_role_session_name)

    # Safety check: ensure we're in the right account
    if expected_account_id:
        actual = _get_account_id(session)
        if actual != expected_account_id:
            raise RuntimeError(
                f"AWS account mismatch. Expected {expected_account_id}, got {actual}. "
                f"Refusing to upload."
            )

    return session.client("s3", region_name=cfg.region, endpoint_url=cfg.endpoint_url)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def upload_file(
    *,
    s3,
    bucket: str,
    key: str,
    local_path: Path,
    content_type: Optional[str] = None,
    cfg: Optional[S3Config] = None,
    extra_metadata: Optional[dict] = None,
) -> None:
    if not local_path.exists():
        raise FileNotFoundError(f"File not found: {local_path}")

    cfg = cfg or S3Config()
    extra_metadata = extra_metadata or {}

    # S3 metadata must be strings
    metadata = {str(k): str(v) for k, v in extra_metadata.items()}
    metadata["sha256"] = _sha256(local_path)

    put_kwargs: dict = {
        "Bucket": bucket,
        "Key": key,
        "Filename": str(local_path),
    }

    extra_args: dict = {"Metadata": metadata}

    if content_type:
        extra_args["ContentType"] = content_type
    
    # Encryption options (optional)
    if cfg.kms_key_id:
        extra_args.update(
            {"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": cfg.kms_key_id}
        )
    elif cfg.use_sse_s3:
        extra_args.update({"ServerSideEncryption": "AES256"})

    put_kwargs["ExtraArgs"] = extra_args
    s3.upload_file(**put_kwargs)


def upload_json_sidecar(
    *,
    s3,
    bucket: str,
    key: str,
    payload: dict,
    cfg: Optional[S3Config] = None,
) -> None:
    """
    Writes a small JSON “sidecar” next to a data file.
    Useful for audit/lineage (and very realistic in data platforms).
    """
    cfg = cfg or S3Config()
    body = json.dumps(payload, indent=2, default=str).encode("utf-8")

    extra_args = {"ContentType": "application/json"}
    if cfg.kms_key_id:
        extra_args.update({"ServerSideEncryption": "aws:kms", "SSEKMSKeyId": cfg.kms_key_id})
    elif cfg.use_sse_s3:
        extra_args.update({"ServerSideEncryption": "AES256"})

    s3.put_object(Bucket=bucket, Key=key, Body=body, **extra_args)


def ensure_bucket_exists(*, s3, bucket: str, region: str) -> None:
    """
    For the simulator, it's convenient to create the bucket if missing.
    On real Trust AWS, you usually won't have permission — but this is optional.
    """
    try:
        s3.head_bucket(Bucket=bucket)
        return
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code not in ("404", "NoSuchBucket", "403"):
            raise

    # Try to create (will fail if you don't have perms — that's fine)
    try:
        if region == "eu-west-1":
            s3.create_bucket(Bucket=bucket)
        else:
            s3.create_bucket(
                Bucket=bucket,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
    except ClientError:
        pass

def cache_object(
    *,
    local_path: Path,
    cache_root: Path,
    bucket: str,
    key: str,
) -> Path:
    """
    Copy a local file to a local cache that mirrors S3 layout:
      data/s3_exports/<bucket>/<key>

    Returns the cached file path.
    """
    if not local_path.exists():
        raise FileNotFoundError(f"Cannot cache missing file: {local_path}")

    dest = cache_root / bucket / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(local_path, dest)
    return dest


def cache_bytes(
    *,
    payload_bytes: bytes,
    cache_root: Path,
    bucket: str,
    key: str,
) -> Path:
    """
    Write arbitrary bytes into the local cache mirroring S3 layout.
    Useful for sidecar JSON created in-memory.
    """
    dest = cache_root / bucket / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload_bytes)
    return dest