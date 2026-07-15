from enum import StrEnum


class RasterProcessingStatus(StrEnum):
    REQUESTED = "requested"
    SCENE_SELECTED = "scene_selected"
    PROCESSING = "processing"
    ARTIFACT_WRITTEN = "artifact_written"
    ASSET_PERSISTED = "asset_persisted"
    COMPLETED = "completed"
    PROCESSED_UNPUBLISHED = "processed_unpublished"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PublicationStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class QualityGateStatus(StrEnum):
    NOT_EVALUATED = "not_evaluated"
    PASSED = "passed"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"


class ValueType(StrEnum):
    CONTINUOUS = "continuous"
    CATEGORICAL = "categorical"
    SPATIAL = "spatial"
    MODEL_ESTIMATE = "model_estimate"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class VerificationRequirement(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    NOT_REQUIRED = "not_required"


class EvidenceRelationType(StrEnum):
    PRIMARY = "primary"
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"
    BASELINE = "baseline"
    CORROBORATING = "corroborating"


class EvidenceVerificationState(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    SUPERSEDED = "superseded"


class AnomalyStatus(StrEnum):
    DETECTED = "detected"
    TRIAGED = "triaged"
    VERIFICATION_REQUESTED = "verification_requested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"
    DIAGNOSIS_PROPOSED = "diagnosis_proposed"
    DECISION_REFERRED = "decision_referred"
    RESOLVED = "resolved"


class DiagnosisAssessmentStatus(StrEnum):
    PENDING = "pending"
    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    REVISED = "revised"
