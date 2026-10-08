import logging
import re
from datetime import date

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.certificate import Certificate
from app.models.enums import CertificateStatus
from app.models.job import GenerationJob
from app.services.certificate_generator import (
    CertificateData,
    CertificateDataError,
    generate_certificate_pdf,
)
from app.services.storage import PdfStorage

logger = logging.getLogger("bulk_cert.certificate_service")


def slugify_recipient_name(name: str) -> str:
    """Sanitize recipient name into a safe filesystem filename slug."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-")
    return clean or "Recipient"


def build_certificate_data(cert: Certificate, job: GenerationJob) -> CertificateData:
    """
    Construct generator input from DB models.
    Single place that maps database entities to CertificateData.
    Reused by background job processor and self-healing generator.
    """
    if not cert.recipient_name or not cert.recipient_name.strip():
        raise CertificateDataError("Recipient name is required")

    if not job.event_name or not job.event_name.strip():
        raise CertificateDataError("Event name is required")

    if not isinstance(job.event_date, date):
        raise CertificateDataError("Invalid event date format")

    if not job.organization_name or not job.organization_name.strip():
        raise CertificateDataError("Organization name is required")

    if not job.authorized_signatory or not job.authorized_signatory.strip():
        raise CertificateDataError("Authorized signatory is required")

    settings = get_settings()
    public_url = (settings.PUBLIC_BASE_URL or "http://localhost:8000").rstrip("/")
    verify_url = f"{public_url}/api/verify/{cert.certificate_id}"

    return CertificateData(
        recipient_name=cert.recipient_name.strip(),
        event_name=job.event_name.strip(),
        event_date=job.event_date,
        organization_name=job.organization_name.strip(),
        authorized_signatory=job.authorized_signatory.strip(),
        certificate_id=cert.certificate_id,
        verify_url=verify_url,
    )


def get_certificate_by_id(db: Session, certificate_id: str) -> Certificate | None:
    """Retrieve a certificate by its unique primary key ID."""
    return db.get(Certificate, certificate_id)


def get_or_regenerate_pdf(db: Session, cert: Certificate, storage: PdfStorage) -> bytes:
    """
    Retrieve certificate PDF from storage or transparently regenerate on demand (self-healing).
    Requires certificate status to be SUCCESS.
    """
    if cert.status != CertificateStatus.SUCCESS:
        raise ValueError(f"Cannot retrieve PDF for certificate with status '{cert.status.value}'")

    # 1. Attempt to read from storage
    if cert.file_path and storage.exists(cert.file_path):
        pdf_bytes = storage.read(cert.file_path)
        if pdf_bytes is not None and pdf_bytes.startswith(b"%PDF"):
            return pdf_bytes

    # 2. Self-heal: Regenerate missing/unreadable file on demand
    logger.warning(
        "Regenerating missing/corrupt PDF file for certificate %s (job %s)",
        cert.certificate_id,
        cert.job_id,
    )

    job = db.get(GenerationJob, cert.job_id)
    if job is None:
        raise ValueError(
            f"Parent job '{cert.job_id}' not found for certificate '{cert.certificate_id}'"
        )

    data = build_certificate_data(cert, job)
    pdf_bytes = generate_certificate_pdf(data)

    rel_path = storage.save(
        job_id=job.job_id,
        cert_id=cert.certificate_id,
        data=pdf_bytes,
    )
    cert.file_path = rel_path
    db.commit()

    logger.info("Successfully regenerated missing file for certificate %s", cert.certificate_id)
    return pdf_bytes
