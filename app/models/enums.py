from enum import StrEnum


class JobStatus(StrEnum):
    """Lifecycle status for a batch certificate generation job."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


class CertificateStatus(StrEnum):
    """Lifecycle status for an individual certificate."""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class FailureType(StrEnum):
    """Classification of certificate generation failure."""

    VALIDATION = "VALIDATION"  # Deterministic input/data issue (non-retryable)
    GENERATION = "GENERATION"  # Transient/rendering error (retryable)
