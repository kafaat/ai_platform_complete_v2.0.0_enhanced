from dataclasses import dataclass
from typing import Any


@dataclass
class PolicyDecision:
    allowed: bool
    reason: str = ""


class PolicyEngine:
    DEFAULT = {"max_nitrogen_kg_ha": 220, "require_human_review_pesticides": True}

    def evaluate(self, recommendation: dict[str, Any], policy=None) -> PolicyDecision:
        p = {**self.DEFAULT, **(policy or {})}
        if recommendation.get("dose_kg_ha", 0) > p["max_nitrogen_kg_ha"]:
            return PolicyDecision(False, "Nitrogen limit exceeded")
        return PolicyDecision(True, "policy passed")
