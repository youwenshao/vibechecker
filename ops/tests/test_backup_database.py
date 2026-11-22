from ops.backup_database import database_environment


def test_session_pooler_uri_becomes_libpq_environment():
    uri = (
        "postgresql://postgres.fixture:one%40two%3Athree%25@pooler.example:6543/staging"
        "?sslmode=verify-full&channel_binding=require&connect_timeout=12"
    )
    assert database_environment(uri) == {
        "PGHOST": "pooler.example",
        "PGPORT": "6543",
        "PGUSER": "postgres.fixture",
        "PGPASSWORD": "one@two:three%",
        "PGDATABASE": "staging",
        "PGSSLMODE": "verify-full",
        "PGCHANNELBINDING": "require",
        "PGCONNECT_TIMEOUT": "12",
    }
