"""Dependency-light production readiness gate for decision safety.

The gate is intentionally conservative. It checks that the project can ship a
field-decision feature only when the Source-of-Truth, replayability, feedback,
and data-quality primitives are present. It does not import optional services.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    severity: str
    detail: str


@dataclass(frozen=True)
class ReadinessReport:
    passed: bool
    checks: list[ReadinessCheck]

    @property
    def failed(self) -> list[ReadinessCheck]:
        return [check for check in self.checks if not check.passed]


def run_decision_readiness_gate(enabled_modules: Iterable[str]) -> ReadinessReport:
    modules = set(enabled_modules)
    required = {
        "canonical_field_state_lock": "P0 Source-of-Truth lock",
        "field_event_sourcing": "P0 replayable field history",
        "field_state_replay_bridge": "P0 replay-to-state bridge",
        "data_quality": "P1 data quality guard",
        "human_feedback_learning": "P1 human feedback loop",
        "feature_store_contract": "P1 feature store contract",
    }
    checks = [
        ReadinessCheck(
            name=module,
            passed=module in modules,
            severity="critical"
            if module.startswith("field") or module.startswith("canonical")
            else "high",
            detail=detail,
        )
        for module, detail in required.items()
    ]
    return ReadinessReport(passed=all(check.passed for check in checks), checks=checks)
