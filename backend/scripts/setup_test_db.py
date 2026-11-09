"""Create and migrate the isolated local test database."""

import os
from pathlib import Path

from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import create_engine, make_url, text

from alembic import command
from scripts.setup_checkpoints import main as setup_checkpoints
from scripts.setup_runtime_db import provision

root = Path(__file__).resolve().parents[2]
config = dotenv_values(root / ".env")
value = config.get("TEST_DATABASE_URL")
runtime_url = config.get("TEST_RUNTIME_DATABASE_URL")
if not value or not runtime_url:
    raise SystemExit("Set TEST_DATABASE_URL in the ignored root .env")
url = make_url(value)
if (url.host, url.port, url.database) != ("127.0.0.1", 55432, "knotdevt_test"):
    raise SystemExit("Expected the dedicated local knotdevt_test database")
with create_engine(
    url.set(database="postgres"), isolation_level="AUTOCOMMIT"
).connect() as conn:
    if not conn.scalar(
        text("SELECT 1 FROM pg_database WHERE datname = 'knotdevt_test'")
    ):
        conn.execute(text("CREATE DATABASE knotdevt_test"))

os.environ["DATABASE_URL"] = value
os.environ["RUNTIME_DATABASE_URL"] = runtime_url
os.chdir(root / "backend")
command.upgrade(Config("alembic.ini"), "head")

provision(value, runtime_url)

setup_checkpoints()
