from datetime import date

from app.config import get_settings
from app.models.certificate import Certificate
from app.models.job import GenerationJob
from app.services.certificate_generator import CertificateData, CertificateDataError


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
