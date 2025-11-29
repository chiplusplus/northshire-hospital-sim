import boto3
from pathlib import Path

def upload_exports_to_s3(local_dir, bucket, prefix):
    s3 = boto3.client("s3")

    for path in Path(local_dir).glob("*.csv"):
        key = f"{prefix}/{path.name}"
        s3.upload_file(str(path), bucket, key)
    print(f"Uploaded files from {local_dir} to s3://{bucket}/{prefix}/")
