from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path


_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="kane-api-test-data-")).resolve()

# Must be set before test modules import app.main/app.store.repositories.
os.environ["OCTOPUS_API_DATA_DIR"] = str(_TEST_DATA_DIR)


def _cleanup_test_data_dir() -> None:
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)


atexit.register(_cleanup_test_data_dir)


def pytest_sessionfinish(session, exitstatus):  # type: ignore[no-untyped-def]
    _cleanup_test_data_dir()
