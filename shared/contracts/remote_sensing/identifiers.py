from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import StringConstraints

TenantId = UUID
FieldId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=128, pattern=r"^fld_[A-Za-z0-9_-]+$"
    ),
]
SeasonId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
SceneId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]

AssetRef = Annotated[str, StringConstraints(pattern=r"^urn:sahool:raster-asset:[A-Za-z0-9_-]+$")]
RasterArtifactRef = Annotated[
    str, StringConstraints(pattern=r"^urn:sahool:raster-artifact:[A-Za-z0-9_-]+$")
]
GeometryRef = Annotated[str, StringConstraints(pattern=r"^urn:sahool:geometry:[A-Za-z0-9_-]+$")]
ObservationRef = Annotated[
    str, StringConstraints(pattern=r"^urn:sahool:observation:[A-Za-z0-9_-]+$")
]
EvidenceRef = Annotated[str, StringConstraints(pattern=r"^urn:sahool:evidence:[A-Za-z0-9_-]+$")]
AnomalyRef = Annotated[str, StringConstraints(pattern=r"^urn:sahool:anomaly:[A-Za-z0-9_-]+$")]
DiagnosisRef = Annotated[str, StringConstraints(pattern=r"^urn:sahool:diagnosis:[A-Za-z0-9_-]+$")]
DecisionReferralRef = Annotated[
    str, StringConstraints(pattern=r"^urn:sahool:decision-referral:[A-Za-z0-9_-]+$")
]
FieldStateRef = Annotated[
    str, StringConstraints(pattern=r"^urn:sahool:field-state:[A-Za-z0-9_-]+$")
]
SoilContextRef = Annotated[
    str, StringConstraints(pattern=r"^urn:sahool:soil-context:[A-Za-z0-9_-]+$")
]
WeatherContextRef = Annotated[
    str, StringConstraints(pattern=r"^urn:sahool:weather-context:[A-Za-z0-9_-]+$")
]
ProcessingRunRef = Annotated[
    str, StringConstraints(pattern=r"^urn:sahool:processing-run:[A-Za-z0-9_-]+$")
]
ModelRef = Annotated[str, StringConstraints(pattern=r"^urn:sahool:model:[A-Za-z0-9_.-]+$")]
UserRef = Annotated[str, StringConstraints(pattern=r"^urn:sahool:user:[A-Za-z0-9_-]+$")]

SchemaVersion = Annotated[str, StringConstraints(pattern=r"^\d+\.\d+\.\d+$")]
ServiceName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{1,62}$")]
SemVer = Annotated[
    str, StringConstraints(pattern=r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
]
EventId = Annotated[str, StringConstraints(pattern=r"^evt_[A-Za-z0-9_-]+$")]
CorrelationId = Annotated[str, StringConstraints(pattern=r"^corr_[A-Za-z0-9_-]+$")]
IdempotencyKey = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=16, max_length=256, pattern=r"^[A-Za-z0-9:._-]+$"
    ),
]
TraceParent = Annotated[
    str, StringConstraints(pattern=r"^[0-9a-f]{2}-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$")
]
Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
