import subprocess
import sys


def test_standalone_worker_registers_all_foreign_key_targets() -> None:
    code = (
        "from app.workers import celery_app; "
        "from app.db.session import Base; "
        "tables = {table.name for table in Base.metadata.sorted_tables}; "
        "assert {'workspaces', 'jobs', 'handover_versions', 'receipts'} <= tables"
    )
    subprocess.run([sys.executable, "-c", code], check=True, timeout=15)
