"""Backward-compatible re-export of the canonical FII chemical-lineage guard.

The canonical implementation was promoted to ``shared/governance/chemical_lineage.py``
so decision-service / actuator-service / odoo-bridge can import the SAME audit at
their own CHEMICAL_INTERVENTION boundaries. Platform callers keep importing
``core.chemical_lineage`` unchanged.
"""

from __future__ import annotations

from shared.governance.chemical_lineage import (  # noqa: F401
    ChemicalBoundary,
    ChemicalLineageAudit,
    ChemicalLineageMode,
    DiagnosisFacts,
    DiagnosisResolver,
    HttpDiagnosisResolver,
    ResolverUnavailable,
    ViolationCode,
    audit_chemical_lineage,
    configured_mode,
)

__all__ = [
    "ChemicalBoundary",
    "ChemicalLineageAudit",
    "ChemicalLineageMode",
    "DiagnosisFacts",
    "DiagnosisResolver",
    "HttpDiagnosisResolver",
    "ResolverUnavailable",
    "ViolationCode",
    "audit_chemical_lineage",
    "configured_mode",
]
