"""Offline ranking evaluation on labeled field-weeks, never probability calibration."""

from __future__ import annotations

from collections import defaultdict

from shared.contracts.remote_sensing.admission import finite_decimal


def evaluate_scouting(*, field_weeks: list[dict], training_fields: set[str], k: int) -> dict:
    """Each row is one held-out field/week, including unavailable observations.

    The caller supplies independently collected labels and a frozen training-field
    manifest. Unlabeled/ineligible rows count against coverage, never as negatives.
    Scores rank scouting priorities; they are not calibrated probabilities.
    """
    if k < 1 or not field_weeks:
        raise ValueError("nonempty_evaluation_and_positive_k_required")
    seen = set()
    groups = defaultdict(list)
    positives = labeled = eligible = 0
    for row in field_weeks:
        key = (row["field_id"], row["week"])
        if key in seen or row["field_id"] in training_fields:
            raise ValueError("duplicate_or_training_field_in_holdout")
        seen.add(key)
        label = row.get("needs_scouting")
        if label is not None and type(label) is not bool:
            raise ValueError("label_must_be_boolean_or_unknown")
        if label is not None:
            labeled += 1
            positives += int(label)
        if row.get("eligible") is not True:
            continue
        score = finite_decimal(row.get("score"))
        if score is None:
            raise ValueError("eligible_row_requires_finite_ranking_score")
        eligible += 1
        groups[row["week"]].append((score, row["field_id"], label))
    selected = []
    for rows in groups.values():
        # Do not rank using the outcome label or remove unlabeled rows before top-K.
        selected.extend(sorted(rows, key=lambda row: (-row[0], row[1]))[:k])
    selected_labeled = [row for row in selected if row[2] is not None]
    tp = sum(row[2] is True for row in selected_labeled)
    fp = sum(row[2] is False for row in selected_labeled)
    return {
        "evaluation_version": "field-held-out-ranking-v1",
        "k_per_week": k,
        "field_weeks": len(field_weeks),
        "selected": len(selected),
        "selected_labeled": len(selected_labeled),
        "precision_at_k_labeled": tp / len(selected_labeled) if selected_labeled else None,
        "recall_at_k_labeled": tp / positives if positives else None,
        "false_alerts_per_100_labeled_field_weeks": 100 * fp / labeled if labeled else None,
        "eligible_coverage": eligible / len(field_weeks),
        "label_coverage": labeled / len(field_weeks),
        "selected_label_coverage": len(selected_labeled) / len(selected) if selected else None,
        "calibration_measured": False,
    }
