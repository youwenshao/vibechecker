"""Stream a PostgreSQL data dump into public-key encryption and retain 14 UTC days."""

import os
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import boto3

DUMP_OPTIONS = [
    "--format=custom",
    "--data-only",
    "--no-acl",
    "--no-owner",
    "--table=auth.users",
    "--table=auth.identities",
    "--table=public.*",
    "--table=private.*",
]


def encrypt_dump(command, recipient, archive, gpg="gpg"):
    with subprocess.Popen(command, stdout=subprocess.PIPE) as dump:
        try:
            subprocess.run(
                [
                    gpg,
                    "--batch",
                    "--compress-algo",
                    "none",
                    "--recipient-file",
                    str(recipient),
                    "--output",
                    str(archive),
                    "--encrypt",
                ],
                stdin=dump.stdout,
                check=True,
            )
        finally:
            dump.stdout.close()
        if dump.wait():
            raise RuntimeError("Database dump failed")


def prune_backups(s3, bucket, today):
    cutoff = today - timedelta(days=14)
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="database/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            try:
                day = date.fromisoformat(key.removeprefix("database/").removesuffix(".dump.gpg"))
            except ValueError:
                continue
            if key == f"database/{day}.dump.gpg" and day <= cutoff:
                s3.delete_object(Bucket=bucket, Key=key)


def main():
    today = datetime.now(UTC).date()
    bucket = os.environ["BACKUP_BUCKET"]
    s3 = boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT_URL"], region_name="auto")
    prune_backups(s3, bucket, today)
    with TemporaryDirectory() as temp:
        recipient, archive = Path(temp) / "recipient.asc", Path(temp) / "backup.gpg"
        recipient.write_text(os.environ["BACKUP_PUBLIC_KEY"], encoding="ascii")
        # PGDATABASE is a connection URI. Passing it by environment keeps credentials out of argv.
        command = [
            "docker",
            "run",
            "--rm",
            "-e",
            "PGDATABASE",
            "--entrypoint",
            "pg_dump",
            "supabase/postgres:17.12.0.002",
            *DUMP_OPTIONS,
        ]
        encrypt_dump(command, recipient, archive)
        s3.upload_file(str(archive), bucket, f"database/{today}.dump.gpg")


if __name__ == "__main__":
    main()
