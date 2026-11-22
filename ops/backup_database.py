"""Stream a PostgreSQL data dump into public-key encryption and retain 14 UTC days."""

import os
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qsl, unquote, urlsplit

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


def database_environment(uri):
    connection = urlsplit(uri)
    if connection.scheme not in {"postgres", "postgresql"} or not connection.hostname:
        raise ValueError("Expected a PostgreSQL connection URI with a hostname")
    settings = {
        "PGHOST": connection.hostname,
        "PGPORT": str(connection.port or 5432),
        "PGUSER": unquote(connection.username or ""),
        "PGPASSWORD": unquote(connection.password or ""),
        "PGDATABASE": unquote(connection.path.lstrip("/")) or "postgres",
    }
    options = {
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "channel_binding": "PGCHANNELBINDING",
        "connect_timeout": "PGCONNECT_TIMEOUT",
        "application_name": "PGAPPNAME",
    }
    for name, value in parse_qsl(connection.query, keep_blank_values=True, strict_parsing=True):
        if name not in options:
            raise ValueError("Unsupported PostgreSQL URI query parameter")
        settings[options[name]] = value
    return settings


def encrypt_dump(command, recipient, archive, gpg="gpg", *, dump_env=None):
    with subprocess.Popen(command, stdout=subprocess.PIPE, env=dump_env) as dump:
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
        # libpq treats PGDATABASE as a literal database name. Forward each setting by name.
        settings = database_environment(os.environ["PGDATABASE"])
        command = [
            "docker",
            "run",
            "--rm",
            *(arg for key in settings for arg in ("-e", key)),
            "--entrypoint",
            "pg_dump",
            "supabase/postgres:17.12.0.002",
            *DUMP_OPTIONS,
        ]
        encrypt_dump(command, recipient, archive, dump_env={**os.environ, **settings})
        s3.upload_file(str(archive), bucket, f"database/{today}.dump.gpg")


if __name__ == "__main__":
    main()
