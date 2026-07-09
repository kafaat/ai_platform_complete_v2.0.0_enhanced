#!/usr/bin/env python3
"""SAHOOL Actuator Service entrypoint.

P2 decomposition shell: runtime state, MQTT/idempotency/saga logic, lifespan, and
router registration live in ``actuator_runtime.py``. This file intentionally keeps
legacy imports stable for tests and launchers. register_routers(app) is executed
by actuator_runtime during app construction.
"""

from __future__ import annotations

from actuator_runtime import *  # noqa: F401,F403
