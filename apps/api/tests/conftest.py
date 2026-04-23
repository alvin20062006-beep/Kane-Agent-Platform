"""
Isolate file-backed stores per pytest process so local dev data under apps/api/data
cannot starve or reorder the background worker queue during tests.
"""

from __future__ import annotations

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="octopus-api-test-")
os.environ["OCTOPUS_API_DATA_DIR"] = _tmp
os.environ["OCTOPUS_PERSISTENCE"] = "file"
os.environ.pop("DATABASE_URL", None)
os.environ.pop("OCTOPUS_DATABASE_URL", None)
