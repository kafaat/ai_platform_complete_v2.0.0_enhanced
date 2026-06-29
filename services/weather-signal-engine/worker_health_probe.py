from __future__ import annotations

import os
import sys
import time
from pathlib import Path

READY_FILE = Path(os.getenv("WORKER_READY_FILE", "/tmp/sahool-worker-ready"))
HEARTBEAT_FILE = Path(os.getenv("WORKER_HEARTBEAT_FILE", "/tmp/sahool-worker-heartbeat"))
MAX_AGE = int(os.getenv("WORKER_HEALTH_MAX_AGE_SEC", "180"))

if not READY_FILE.exists():
    print("not ready: ready file missing")
    sys.exit(1)
if HEARTBEAT_FILE.exists() and time.time() - HEARTBEAT_FILE.stat().st_mtime > MAX_AGE:
    print("not ready: heartbeat stale")
    sys.exit(1)
print("ready")
