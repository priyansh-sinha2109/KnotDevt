"""Provision the non-owner login for the dedicated local KnotDevt databases."""

from psycopg import Connection, sql
from sqlalchemy import make_url

from app.core.config import settings

ROLE = "knotdevt_app"


def provision(owner_url: str, runtime_url: str) -> None:
    owner = make_url(owner_url)
    runtime = make_url(runtime_url)
    if (
        (owner.host, owner.port, owner.database)
        not in {
            ("127.0.0.1", 55432, "knotdevt"),
            ("127.0.0.1", 55432, "knotdevt_test"),
        }
        or (owner.host, owner.port, owner.database)
        != (
            runtime.host,
            runtime.port,
            runtime.database,
        )
        or runtime.username != ROLE
        or not runtime.password
    ):
        raise SystemExit(
            "Expected dedicated local KnotDevt database and application role"
        )

    dsn = owner.set(drivername="postgresql").render_as_string(hide_password=False)
    with Connection.connect(dsn) as conn:
        if not conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (ROLE,)
        ).fetchone():
            conn.execute(
                sql.SQL(
                    "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOBYPASSRLS PASSWORD {}"
                ).format(sql.Identifier(ROLE), sql.Literal(runtime.password))
            )
        privileges = sql.SQL("SELECT, INSERT, UPDATE, DELETE")
        role = sql.Identifier(ROLE)
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(role))
        conn.execute(
            sql.SQL("GRANT USAGE, CREATE ON SCHEMA agent_checkpoints TO {}").format(
                role
            )
        )
        conn.execute(
            sql.SQL("GRANT {} ON ALL TABLES IN SCHEMA public TO {}").format(
                privileges, role
            )
        )
        conn.execute(
            sql.SQL(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT {} ON TABLES TO {}"
            ).format(privileges, role)
        )


if __name__ == "__main__":
    config = settings()
    provision(
        config.database_url.get_secret_value(),
        config.runtime_database_url.get_secret_value(),
    )
