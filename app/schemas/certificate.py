from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import CertificateStatus, FailureType


class CertificateOut(BaseModel):
    """Detailed certificate representation."""

    certificate_id: str
    row_number: int
    recipient_name: str
    recipient_email: str | None = None
    status: CertificateStatus
    failure_type: FailureType | None = None
    error_message: str | None = None
    attempts: int
    view_url: str | None = None
    download_url: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_certificate_model(cls, cert: Any) -> "CertificateOut":
        """Construct CertificateOut, setting view/download URLs only when SUCCESS."""
        is_success = cert.status == CertificateStatus.SUCCESS
        return cls(
            certificate_id=cert.certificate_id,
            row_number=cert.row_number,
            recipient_name=cert.recipient_name,
            recipient_email=cert.recipient_email,
            status=cert.status,
            failure_type=cert.failure_type,
            error_message=cert.error_message,
            attempts=cert.attempts,
            view_url=(f"/api/certificates/{cert.certificate_id}/view" if is_success else None),
            download_url=(
                f"/api/certificates/{cert.certificate_id}/download" if is_success else None
            ),
            created_at=cert.created_at,
            completed_at=cert.completed_at,
        )


class CertificateListOut(BaseModel):
    """Paginated list of certificates for a job."""

    job_id: str
    total: int
    limit: int
    offset: int
    certificates: list[CertificateOut]


class VerifyOut(BaseModel):
    """Public certificate verification response (no email returned)."""

    valid: bool = True
    certificate_id: str
    recipient_name: str
    event_name: str
    event_date: date
    organization_name: str
    issued_at: datetime
