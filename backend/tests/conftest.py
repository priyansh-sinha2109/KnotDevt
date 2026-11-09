import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import make_url

root = Path(__file__).resolve().parents[2]
test_url = os.environ.get("TEST_DATABASE_URL") or dotenv_values(root / ".env").get(
    "TEST_DATABASE_URL"
)
if not test_url:
    raise RuntimeError("Configure TEST_DATABASE_URL and run scripts/setup_test_db.py")
url = make_url(test_url)
if (url.host, url.port, url.database) != ("127.0.0.1", 55432, "knotdevt_test"):
    raise RuntimeError("Integration tests require the isolated KnotDevt test database")
runtime = dotenv_values(root / ".env").get("TEST_RUNTIME_DATABASE_URL")
if (
    not runtime
    or make_url(runtime).set(username=url.username, password=url.password) != url
):
    raise RuntimeError("Integration tests require the isolated runtime URL")
os.environ["DATABASE_URL"] = test_url
os.environ["RUNTIME_DATABASE_URL"] = runtime
os.environ["REDIS_URL"] = "redis://127.0.0.1:56379/15"
os.environ["LLM_PROVIDER"] = "fake"
