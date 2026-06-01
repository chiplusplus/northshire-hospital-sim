"""Upload simulation queue day-folders to Trust S3."""

from __future__ import annotations

import io
from datetime import date
from typing import Any, Dict

import pandas as pd


def publish_simulation_queue(
    *,
    s3: Any,
    bucket: str,
    queue: Dict[date, Dict[str, pd.DataFrame]],
    prefix: str = "_simulation_queue",
) -> int:
    """Upload each day's CSVs to s3://{bucket}/{prefix}/day=YYYY-MM-DD/{filename}.

    Returns count of files uploaded.
    """
    uploaded = 0

    for day in sorted(queue.keys()):
        files = queue[day]
        day_prefix = f"{prefix}/day={day.isoformat()}"

        for filename, df in files.items():
            buf = io.BytesIO()
            df.to_csv(buf, index=False)
            buf.seek(0)

            s3.put_object(
                Bucket=bucket,
                Key=f"{day_prefix}/{filename}",
                Body=buf.getvalue(),
                ContentType="text/csv",
            )
            uploaded += 1

    return uploaded
