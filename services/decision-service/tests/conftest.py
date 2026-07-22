from __future__ import annotations

import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

# Condition-1 determinism: the activation gate reads its build identity from DEPLOY_BUILD_SHA
# and fails closed if it is absent or not valid hex. Tests that don't exercise that failure
# path need a stable, valid 64-hex build identity; pin one deterministically here (a fixed
# value, never Date/random) so the whole suite runs against one known build fingerprint.
# Tests that assert the fail-closed behavior monkeypatch/delenv it locally.
os.environ.setdefault("DEPLOY_BUILD_SHA", "d" * 40)
os.environ.setdefault("ACTIVATION_EVIDENCE_SIGNING_KEY", "evidence-key")
