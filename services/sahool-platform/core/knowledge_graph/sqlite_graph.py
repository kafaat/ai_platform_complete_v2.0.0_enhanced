"""Deprecated compatibility tombstone for ARCH-S4 Knowledge Graph ownership.

The physical Knowledge Graph store is owned by ``services/knowledge-graph/kg_store.py``.
No production code may import a KG store implementation from sahool-platform.
This module intentionally exports no store classes.
"""

from __future__ import annotations

DEPRECATED_KG_STORE_LOCATION = "services/knowledge-graph/kg_store.py"
