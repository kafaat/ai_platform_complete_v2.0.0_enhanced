"""Human review fork/compare workflow for agronomist recommendations.

Forks compare evidence assumptions; they do not replace Canonical Field State or
Recommendation Engine. An approved fork still goes through normal publication.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import unified_diff
from typing import Literal

ForkStatus = Literal["draft", "approved", "rejected"]


@dataclass(frozen=True)
class RecommendationFork:
    fork_id: str
    base_recommendation_id: str
    label: str
    evidence_policy: str
    body_ar: str
    status: ForkStatus = "draft"
    reviewer_notes: list[str] = field(default_factory=list)

    @property
    def task(self) -> None:
        raise AttributeError("Review forks must not create tasks directly")


@dataclass(frozen=True)
class ForkComparison:
    base_recommendation_id: str
    left_id: str
    right_id: str
    diff_text: str
    changed: bool


class ReviewForkManager:
    def fork(
        self, base_recommendation_id: str, label: str, body_ar: str, evidence_policy: str
    ) -> RecommendationFork:
        safe_label = label.strip().lower().replace(" ", "-")[:40] or "fork"
        return RecommendationFork(
            fork_id=f"{base_recommendation_id}:{safe_label}",
            base_recommendation_id=base_recommendation_id,
            label=label,
            evidence_policy=evidence_policy,
            body_ar=body_ar,
        )

    def compare(self, left: RecommendationFork, right: RecommendationFork) -> ForkComparison:
        diff = "\n".join(
            unified_diff(
                left.body_ar.splitlines(),
                right.body_ar.splitlines(),
                fromfile=left.fork_id,
                tofile=right.fork_id,
                lineterm="",
            )
        )
        return ForkComparison(
            base_recommendation_id=left.base_recommendation_id,
            left_id=left.fork_id,
            right_id=right.fork_id,
            diff_text=diff,
            changed=left.body_ar != right.body_ar or left.evidence_policy != right.evidence_policy,
        )

    def approve(self, fork: RecommendationFork, note: str) -> RecommendationFork:
        return RecommendationFork(
            fork_id=fork.fork_id,
            base_recommendation_id=fork.base_recommendation_id,
            label=fork.label,
            evidence_policy=fork.evidence_policy,
            body_ar=fork.body_ar,
            status="approved",
            reviewer_notes=[*fork.reviewer_notes, note],
        )
