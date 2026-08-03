"""Canonical crop phenology state for a field season.

This module reconciles calendar age, weather-owned accumulated GDD, field
observations, and optional remote-sensing evidence.  It deliberately separates
an observed stage from a predicted stage and never lets satellite evidence
silently become a field observation.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from core.crop_cards.loader import load_crop_card
from core.gdd_phenology import phenology_progress
from core.season_phenology import current_stage, resolve_crop_id

ObservationSource = Literal["field_scout", "agronomist", "farmer", "sensor"]
StateStatus = Literal["observed", "predicted", "blocked"]

_SOURCE_PRIORITY: dict[str, int] = {
    "agronomist": 4,
    "field_scout": 3,
    "farmer": 2,
    "sensor": 1,
}


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(UTC)


def _finite(
    value: float, name: str, *, minimum: float | None = None, maximum: float | None = None
) -> float:
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and out < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and out > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return out


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_sha(value: str) -> str:
    normalized = value.lower().strip()
    if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
        raise ValueError("evidence_digest must be a 64-character SHA-256")
    return normalized


@dataclass(frozen=True)
class PhenologyObservation:
    observation_id: str
    source: ObservationSource
    stage: str
    observed_at: datetime
    confidence: float
    evidence_digest: str

    def normalized(self) -> PhenologyObservation:
        if not self.observation_id.strip():
            raise ValueError("observation_id is required")
        if self.source not in _SOURCE_PRIORITY:
            raise ValueError(f"unsupported observation source: {self.source}")
        if not self.stage.strip():
            raise ValueError("stage is required")
        return PhenologyObservation(
            observation_id=self.observation_id.strip(),
            source=self.source,
            stage=self.stage.strip(),
            observed_at=_aware(self.observed_at, "observed_at"),
            confidence=_finite(self.confidence, "confidence", minimum=0.0, maximum=1.0),
            evidence_digest=_valid_sha(self.evidence_digest),
        )


@dataclass(frozen=True)
class RemoteSensingStageEvidence:
    stage: str
    observed_at: datetime
    confidence: float
    evidence_digest: str

    def normalized(self) -> RemoteSensingStageEvidence:
        if not self.stage.strip():
            raise ValueError("remote-sensing stage is required")
        return RemoteSensingStageEvidence(
            stage=self.stage.strip(),
            observed_at=_aware(self.observed_at, "remote_sensing_observed_at"),
            confidence=_finite(
                self.confidence, "remote_sensing_confidence", minimum=0.0, maximum=1.0
            ),
            evidence_digest=_valid_sha(self.evidence_digest),
        )


@dataclass(frozen=True)
class CanonicalPhenologyState:
    tenant_id: str
    field_id: str
    season_id: str
    crop_id: str
    cultivar_id: str | None
    as_of: datetime
    sowing_date: date
    days_since_sowing: int
    observed_stage: str | None
    predicted_stage: str | None
    canonical_stage: str | None
    status: StateStatus
    confidence: float | None
    accumulated_gdd: float | None
    gdd_fraction: float | None
    stage_divergence: str
    observation_ids: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    limitations: tuple[str, ...]
    state_digest: str


def _crop_stages(crop_id: str) -> tuple[str, ...]:
    card = load_crop_card(crop_id)
    stages = tuple(
        str(item.get("stage", "")).strip()
        for item in (card or {}).get("phenology", {}).get("stages", [])
    )
    return tuple(stage for stage in stages if stage)


def _choose_observation(
    observations: Iterable[PhenologyObservation],
    *,
    as_of: datetime,
    valid_stages: set[str],
    max_age_days: int,
    minimum_confidence: float,
) -> tuple[PhenologyObservation | None, tuple[str, ...], tuple[str, ...]]:
    accepted: list[PhenologyObservation] = []
    limitations: list[str] = []
    ids: list[str] = []
    seen_ids: set[str] = set()
    for raw in observations:
        obs = raw.normalized()
        if obs.observation_id in seen_ids:
            raise ValueError(f"duplicate observation_id: {obs.observation_id}")
        seen_ids.add(obs.observation_id)
        ids.append(obs.observation_id)
        if obs.observed_at > as_of:
            limitations.append(f"FUTURE_OBSERVATION:{obs.observation_id}")
            continue
        if obs.stage not in valid_stages:
            limitations.append(f"UNKNOWN_STAGE:{obs.observation_id}")
            continue
        if obs.confidence < minimum_confidence:
            limitations.append(f"LOW_CONFIDENCE_OBSERVATION:{obs.observation_id}")
            continue
        if as_of - obs.observed_at > timedelta(days=max_age_days):
            limitations.append(f"STALE_OBSERVATION:{obs.observation_id}")
            continue
        accepted.append(obs)

    if not accepted:
        return None, tuple(ids), tuple(sorted(set(limitations)))

    accepted.sort(
        key=lambda item: (
            item.observed_at,
            item.confidence,
            _SOURCE_PRIORITY[item.source],
            item.observation_id,
        ),
        reverse=True,
    )
    winner = accepted[0]
    conflict_window = timedelta(days=7)
    conflicts = [
        item
        for item in accepted[1:]
        if winner.observed_at - item.observed_at <= conflict_window and item.stage != winner.stage
    ]
    if conflicts:
        limitations.append("CONFLICTING_HIGH_CONFIDENCE_OBSERVATIONS")
        return None, tuple(ids), tuple(sorted(set(limitations)))
    return winner, tuple(ids), tuple(sorted(set(limitations)))


def build_canonical_phenology_state(
    *,
    tenant_id: str,
    field_id: str,
    season_id: str,
    crop: str,
    cultivar_id: str | None,
    sowing_date: date,
    as_of: datetime,
    accumulated_gdd: float | None = None,
    observations: Iterable[PhenologyObservation] = (),
    remote_sensing: RemoteSensingStageEvidence | None = None,
    observation_max_age_days: int = 21,
    observation_min_confidence: float = 0.70,
) -> CanonicalPhenologyState:
    """Build one immutable, evidence-linked phenology state.

    Field observations are authoritative when recent, valid, and non-conflicting.
    Otherwise the state falls back to a weather/calendar prediction. Remote-
    sensing evidence may increase confidence when it agrees, but never overrides
    a field observation by itself.
    """
    for name, value in (
        ("tenant_id", tenant_id),
        ("field_id", field_id),
        ("season_id", season_id),
        ("crop", crop),
    ):
        if not str(value).strip():
            raise ValueError(f"{name} is required")
    now = _aware(as_of, "as_of")
    if sowing_date > now.date():
        raise ValueError("sowing_date cannot be after as_of")
    if observation_max_age_days < 1:
        raise ValueError("observation_max_age_days must be >= 1")
    _finite(observation_min_confidence, "observation_min_confidence", minimum=0.0, maximum=1.0)
    if accumulated_gdd is not None:
        accumulated_gdd = _finite(accumulated_gdd, "accumulated_gdd", minimum=0.0)

    crop_id = resolve_crop_id(crop)
    limitations: list[str] = []
    if crop_id is None:
        crop_id = crop.strip().lower()
        limitations.append("UNKNOWN_CROP_CARD")
    valid_stages = set(_crop_stages(crop_id))
    days_since_sowing = (now.date() - sowing_date).days

    selected, observation_ids, observation_limits = _choose_observation(
        observations,
        as_of=now,
        valid_stages=valid_stages,
        max_age_days=observation_max_age_days,
        minimum_confidence=observation_min_confidence,
    )
    limitations.extend(observation_limits)

    calendar = current_stage(crop_id, days_since_sowing)
    progress = phenology_progress(crop_id, days_since_sowing, accumulated_gdd)
    predicted_stage = progress.get("gdd_stage") or (calendar or {}).get("stage")
    if predicted_stage is None:
        limitations.append("PREDICTED_STAGE_UNAVAILABLE")

    observed_stage = selected.stage if selected else None
    status: StateStatus
    canonical_stage: str | None
    confidence: float | None
    if "CONFLICTING_HIGH_CONFIDENCE_OBSERVATIONS" in limitations:
        status, canonical_stage, confidence = "blocked", None, None
    elif selected is not None:
        status, canonical_stage, confidence = "observed", selected.stage, selected.confidence
    elif predicted_stage is not None:
        status, canonical_stage = "predicted", predicted_stage
        confidence = 0.65 if progress.get("gdd_stage") else 0.45
    else:
        status, canonical_stage, confidence = "blocked", None, None

    evidence_digests = [selected.evidence_digest] if selected else []
    remote = remote_sensing.normalized() if remote_sensing else None
    if remote:
        if remote.observed_at > now:
            limitations.append("FUTURE_REMOTE_SENSING_EVIDENCE")
        elif remote.stage not in valid_stages:
            limitations.append("UNKNOWN_REMOTE_SENSING_STAGE")
        else:
            evidence_digests.append(remote.evidence_digest)
            if canonical_stage and remote.stage == canonical_stage:
                confidence = min(1.0, round((confidence or 0.0) + 0.10 * remote.confidence, 3))
            elif canonical_stage and remote.confidence >= 0.70:
                limitations.append("REMOTE_SENSING_STAGE_DIVERGENCE")

    divergence = "unknown"
    if observed_stage and predicted_stage:
        divergence = "aligned" if observed_stage == predicted_stage else "observed_vs_predicted"
    elif progress.get("divergence"):
        divergence = str(progress["divergence"].get("direction", "unknown"))

    base = {
        "tenant_id": tenant_id,
        "field_id": field_id,
        "season_id": season_id,
        "crop_id": crop_id,
        "cultivar_id": cultivar_id,
        "as_of": now.isoformat(),
        "sowing_date": sowing_date.isoformat(),
        "days_since_sowing": days_since_sowing,
        "observed_stage": observed_stage,
        "predicted_stage": predicted_stage,
        "canonical_stage": canonical_stage,
        "status": status,
        "confidence": confidence,
        "accumulated_gdd": accumulated_gdd,
        "gdd_fraction": progress.get("gdd_fraction"),
        "stage_divergence": divergence,
        "observation_ids": sorted(observation_ids),
        "evidence_digests": sorted(set(evidence_digests)),
        "limitations": sorted(set(limitations)),
    }
    return CanonicalPhenologyState(
        tenant_id=tenant_id,
        field_id=field_id,
        season_id=season_id,
        crop_id=crop_id,
        cultivar_id=cultivar_id,
        as_of=now,
        sowing_date=sowing_date,
        days_since_sowing=days_since_sowing,
        observed_stage=observed_stage,
        predicted_stage=predicted_stage,
        canonical_stage=canonical_stage,
        status=status,
        confidence=confidence,
        accumulated_gdd=accumulated_gdd,
        gdd_fraction=progress.get("gdd_fraction"),
        stage_divergence=divergence,
        observation_ids=tuple(sorted(observation_ids)),
        evidence_digests=tuple(sorted(set(evidence_digests))),
        limitations=tuple(sorted(set(limitations))),
        state_digest=_digest(base),
    )


def state_payload(state: CanonicalPhenologyState) -> dict[str, object]:
    payload = asdict(state)
    payload["as_of"] = state.as_of.isoformat()
    payload["sowing_date"] = state.sowing_date.isoformat()
    return payload
