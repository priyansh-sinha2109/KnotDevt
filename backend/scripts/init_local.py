"""Generate credentials for the dedicated local Compose project."""

import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[2]
password = secrets.token_hex(32)
signing_key = secrets.token_hex(32)
db = f"postgresql+psycopg://knotdevt:{password}@127.0.0.1:55432/knotdevt"
try:
    with (root / ".env").open("x", encoding="utf-8") as config:
        config.write(
            f"POSTGRES_PASSWORD={password}\n"
            f"DATABASE_URL={db}\n"
            f"TEST_DATABASE_URL={db}_test\n"
            f"SESSION_SIGNING_SECRET={signing_key}\n"
        )
except FileExistsError:
    raise SystemExit("Local .env already exists") from None
