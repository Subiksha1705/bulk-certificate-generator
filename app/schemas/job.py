from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.config import get_settings
from app.constants import (
    MAX_EVENT_DATE,
    MAX_EVENT_NAME_LENGTH,
    MAX_ORGANIZATION_NAME_LENGTH,
    MAX_SIGNATORY_LENGTH,
    MIN_EVENT_DATE,
    MIN_EVENT_NAME_LENGTH,
    MIN_ORGANIZATION_NAME_LENGTH,
    MIN_SIGNATORY_LENGTH,
)
from app.models.enums import JobStatus
from app.services.certificate_generator import CertificateDataError, validate_text_renderable
from app.services.validation import normalize_text


class RecipientIn(BaseModel):
    """Input recipient data. Extra fields are ignored to tolerate client variations."""

    name: str | None = None
    email: str | None = None

    model_config = ConfigDict(extra="ignore")


class JobCreate(BaseModel):
    """Payload for submitting a batch certificate generation job."""

    event_name: str
    event_date: date
    organization_name: str
    authorized_signatory: str
    recipients: list[RecipientIn]

    model_config = ConfigDict(extra="forbid")

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, value: str) -> str:
        norm = normalize_text(value)
        if not (MIN_EVENT_NAME_LENGTH <= len(norm) <= MAX_EVENT_NAME_LENGTH):
            raise ValueError(
                f"event_name must be {MIN_EVENT_NAME_LENGTH}–{MAX_EVENT_NAME_LENGTH} chars"
            )
        try:
            validate_text_renderable(norm, "event_name")
        except CertificateDataError as e:
            raise ValueError(str(e)) from e
        return norm

    @field_validator("event_date")
    @classmethod
    def validate_event_date(cls, value: date) -> date:
        if not (MIN_EVENT_DATE <= value <= MAX_EVENT_DATE):
            msg = (
                f"event_date must be between {MIN_EVENT_DATE.isoformat()} "
                f"and {MAX_EVENT_DATE.isoformat()}"
            )
            raise ValueError(msg)
        return value

    @field_validator("organization_name")
    @classmethod
    def validate_organization_name(cls, value: str) -> str:
        norm = normalize_text(value)
        if not (MIN_ORGANIZATION_NAME_LENGTH <= len(norm) <= MAX_ORGANIZATION_NAME_LENGTH):
            msg = (
                f"organization_name must be {MIN_ORGANIZATION_NAME_LENGTH}–"
                f"{MAX_ORGANIZATION_NAME_LENGTH} chars"
            )
            raise ValueError(msg)
        try:
            validate_text_renderable(norm, "organization_name")
        except CertificateDataError as e:
            raise ValueError(str(e)) from e
        return norm

    @field_validator("authorized_signatory")
    @classmethod
    def validate_authorized_signatory(cls, value: str) -> str:
        norm = normalize_text(value)
        if not (MIN_SIGNATORY_LENGTH <= len(norm) <= MAX_SIGNATORY_LENGTH):
            msg = (
                f"authorized_signatory must be {MIN_SIGNATORY_LENGTH}–{MAX_SIGNATORY_LENGTH} chars"
            )
            raise ValueError(msg)
        try:
            validate_text_renderable(norm, "authorized_signatory")
        except CertificateDataError as e:
            raise ValueError(str(e)) from e
        return norm

    @field_validator("recipients")
    @classmethod
    def validate_recipients_list(cls, value: list[RecipientIn]) -> list[RecipientIn]:
        if not value:
            raise ValueError("recipients list cannot be empty")
        max_recipients = get_settings().MAX_RECIPIENTS_PER_JOB
        if len(value) > max_recipients:
            raise ValueError(f"recipients list cannot exceed {max_recipients} items")
        return value


class JobLinks(BaseModel):
    """Hypermedia navigation links for a job."""

    self: str
    certificates: str


class JobOut(BaseModel):
    """Job status and summary output schema."""

    job_id: str
    status: JobStatus
    event_name: str
    event_date: date
    organization_name: str
    authorized_signatory: str
    total: int
    processed: int
    successful: int
    failed: int
    progress_percentage: float
    created_at: datetime
    completed_at: datetime | None = None
    links: JobLinks

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_job_model(cls, job: Any) -> "JobOut":
        """Build JobOut response from a GenerationJob ORM model."""
        total = job.total_recipients
        processed = job.processed_count
        progress = round((processed / total) * 100, 1) if total > 0 else 0.0

        return cls(
            job_id=job.job_id,
            status=job.status,
            event_name=job.event_name,
            event_date=job.event_date,
            organization_name=job.organization_name,
            authorized_signatory=job.authorized_signatory,
            total=total,
            processed=processed,
            successful=job.successful_count,
            failed=job.failed_count,
            progress_percentage=progress,
            created_at=job.created_at,
            completed_at=job.completed_at,
            links=JobLinks(
                self=f"/api/jobs/{job.job_id}",
                certificates=f"/api/jobs/{job.job_id}/certificates",
            ),
        )


class JobCreateResponse(JobOut):
    """Response returned upon POST /api/jobs/ creation or replay."""

    idempotent_replay: bool = False

    @classmethod
    def from_job_model(cls, job: Any, idempotent_replay: bool = False) -> "JobCreateResponse":
        base = JobOut.from_job_model(job)
        return cls(**base.model_dump(), idempotent_replay=idempotent_replay)


class JobRetryResponse(BaseModel):
    """Response returned upon POST /api/jobs/{id}/retry-failed."""

    job_id: str
    retried_count: int
    skipped_non_retryable: int
    status: JobStatus

    model_config = ConfigDict(from_attributes=True)
