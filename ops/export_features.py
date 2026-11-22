"""Export closed UTC days to the private features/ prefix. Replays replace the same day."""

import io
import os
from datetime import UTC, datetime, timedelta

import boto3
import httpx
import pyarrow as pa
import pyarrow.parquet as pq
from dateutil.relativedelta import relativedelta

SIGNALS = ("e1", "e2", "e3", "e4", "e5", "e6", "e7", "stylometry")
SCHEMA = pa.schema(
    [("mode", pa.string()), ("engine_version", pa.string()), *((s, pa.float64()) for s in SIGNALS)]
)


def export_day(api, bucket, s3, day):
    cursor = 0
    output = io.BytesIO()
    with pq.ParquetWriter(output, SCHEMA) as writer:
        while True:
            response = api.get(
                "feature_log",
                params={
                    "select": "sequence,mode,engine_version,features",
                    "day": f"eq.{day}",
                    "sequence": f"gt.{cursor}",
                    "order": "sequence.asc",
                    "limit": 500,
                },
            )
            response.raise_for_status()
            batch = response.json()
            if not batch:
                break
            rows = [
                {
                    "mode": r["mode"],
                    "engine_version": r["engine_version"],
                    **{s: r["features"].get(s) for s in SIGNALS},
                }
                for r in batch
            ]
            writer.write_table(pa.Table.from_pylist(rows, schema=SCHEMA))
            cursor = batch[-1]["sequence"]
    if cursor:
        s3.put_object(Bucket=bucket, Key=f"features/{day}.parquet", Body=output.getvalue())


def main():
    today = datetime.now(UTC).date()
    token = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    headers = {"apikey": token}
    if not token.startswith("sb_secret_"):
        headers["authorization"] = "Bearer " + token
    bucket = os.environ["R2_BUCKET"]
    s3 = boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT_URL"], region_name="auto")
    # Retry the entire retained window after a missed scheduled run.
    with httpx.Client(base_url=os.environ["SUPABASE_URL"] + "/rest/v1/", headers=headers) as api:
        for days_ago in range(6, 0, -1):
            export_day(api, bucket, s3, today - timedelta(days=days_ago))
    cutoff = today - relativedelta(months=12)
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="features/"):
        for obj in page.get("Contents", []):
            name = obj["Key"]
            try:
                day = datetime.strptime(name, "features/%Y-%m-%d.parquet").date()
            except ValueError:
                continue
            if day <= cutoff:
                s3.delete_object(Bucket=bucket, Key=name)


if __name__ == "__main__":
    main()
