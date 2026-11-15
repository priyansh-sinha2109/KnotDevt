import subprocess
import sys


def test_standalone_worker_registers_all_foreign_key_targets() -> None:
    code = (
        "from app.workers import celery_app; "
        "from app.db.session import Base; "
        "tables = {table.name for table in Base.metadata.sorted_tables}; "
        "assert {'workspaces', 'jobs', 'handover_versions', 'receipts'} <= tables"
    )
    # This checks metadata completeness, not a startup performance budget.
    # Cold Windows imports of the existing AI libraries can exceed 15 seconds.
    subprocess.run([sys.executable, "-c", code], check=True, timeout=60)
