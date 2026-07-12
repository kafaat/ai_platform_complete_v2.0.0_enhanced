#!/usr/bin/env python3
"""SAHOOL Actuator Service entrypoint.

P2 decomposition shell: runtime state, MQTT/idempotency/saga logic, lifespan, and
router registration live in ``actuator_runtime.py``. This file intentionally keeps
legacy imports stable for tests, routers, and launchers.

Unlike ``from actuator_runtime import *``, this compatibility export also preserves
private helper names (``_verify_token``, ``_safety_status``, feature gates, etc.).
Those helpers are part of the service's established internal contract and are used
by routers and safety guards. Dropping them silently weakens test coverage and can
break dependency overrides in the decomposed application.
"""

from __future__ import annotations

import actuator_runtime as _runtime

# Re-export the complete runtime compatibility surface, including single-underscore
# helpers, while excluding only Python module metadata. Keep object identity intact
# so FastAPI dependency overrides target the exact callable mounted on routes.
for _name, _value in vars(_runtime).items():
    if not _name.startswith("__"):
        globals()[_name] = _value

# Re-run router registration when this compatibility shell is loaded against an
# already-cached runtime module. This matters in monorepo test processes where a
# prior import may have resolved a different top-level ``routers`` package. The
# registry is idempotent by path+methods, so normal service startup is unaffected.
_runtime.register_routers(_runtime.app)

# Avoid exposing the temporary loop variables as part of the compatibility surface.
del _name, _value
