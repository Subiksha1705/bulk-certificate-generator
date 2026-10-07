from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.certificate import Certificate
from app.models.enums import CertificateStatus, FailureType, JobStatus
from app.models.job import GenerationJob
from app.schemas.job import JobCreate
from app.services.fingerprint import compute_request_hash
from app.services.validation import validate_recipients
from app.utils.ids import generate_certificate_id, generate_job_id


def utcnow() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(UTC)


def recompute_counts(db: Session, job: GenerationJob) -> None:
    """
    Recompute job counters directly from certificate rows.
    Self-correcting and accurate across retries, crash recovery, and race conditions.
    """
    counts_query = (
        select(Certificate.status, func.count(Certificate.certificate_id))
        .where(Certificate.job_id == job.job_id)
        .group_by(Certificate.status)
    )
    status_counts = dict(db.execute(counts_query).all())

    job.successful_count = status_counts.get(CertificateStatus.SUCCESS, 0)
    job.failed_count = status_counts.get(CertificateStatus.FAILED, 0)
    job.processed_count = job.successful_count + job.failed_count


def get_job_by_id(db: Session, job_id: str) -> GenerationJob | None:
    """Query a GenerationJob by its primary key ID."""
    return db.get(GenerationJob, job_id)


def create_job(db: Session, payload: JobCreate) -> tuple[GenerationJob, bool]:
    """
    Create a new batch certificate job or return an existing one (idempotency).
    Returns (job, created_flag) where created_flag is True for new jobs and False for replays.
    """
    # 1. Compute deterministic request hash
    request_hash = compute_request_hash(payload)

    # 2. Check for existing job (idempotency check)
    existing_job = db.scalars(
        select(GenerationJob).where(GenerationJob.request_hash == request_hash)
    ).first()
    if existing_job is not None:
        return existing_job, False

    # 3. Validate recipients and detect batch duplicates
    recipient_checks = validate_recipients(payload.recipients)

    # 4. Construct GenerationJob record
    job_id = generate_job_id()
    now = utcnow()
    job = GenerationJob(
        job_id=job_id,
        event_name=payload.event_name,
        event_date=payload.event_date,
        organization_name=payload.organization_name,
        authorized_signatory=payload.authorized_signatory,
        status=JobStatus.PENDING,
        total_recipients=len(recipient_checks),
        request_hash=request_hash,
        created_at=now,
    )

    # 5. Construct Certificate rows
    certificates: list[Certificate] = []
    valid_count = 0

    for check in recipient_checks:
        cert_id = generate_certificate_id()
        if check.is_valid:
            valid_count += 1
            cert = Certificate(
                certificate_id=cert_id,
                job_id=job_id,
                row_number=check.row_number,
                recipient_name=check.name,
                recipient_email=check.email,
                status=CertificateStatus.PENDING,
                failure_type=None,
                error_message=None,
                attempts=0,
                created_at=now,
            )
        else:
            cert = Certificate(
                certificate_id=cert_id,
                job_id=job_id,
                row_number=check.row_number,
                recipient_name=check.name,
                recipient_email=check.email,
                status=CertificateStatus.FAILED,
                failure_type=FailureType.VALIDATION,
                error_message=check.error_message,
                attempts=0,
                created_at=now,
                completed_at=now,
            )
        certificates.append(cert)

    job.certificates = certificates
    db.add(job)

    # 6. Recompute initial counters
    job.failed_count = len(recipient_checks) - valid_count
    job.successful_count = 0
    job.processed_count = job.failed_count

    # If all recipients are invalid at intake, mark job FAILED immediately
    if valid_count == 0:
        job.status = JobStatus.FAILED
        job.completed_at = now

    # 7. Commit with race-safe IntegrityError handling
    try:
        db.commit()
        db.refresh(job)
        return job, True
    except IntegrityError:
        db.rollback()
        winner_job = db.scalars(
            select(GenerationJob).where(GenerationJob.request_hash == request_hash)
        ).first()
        if winner_job is not None:
            return winner_job, False
        raise


def list_certificates(
    db: Session,
    job_id: str,
    status: CertificateStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[Certificate]]:
    """
    List certificates for a job with optional status filtering and pagination.
    Returns (matching_total_count, certificates_page).
    """
    base_query = select(Certificate).where(Certificate.job_id == job_id)
    if status is not None:
        base_query = base_query.where(Certificate.status == status)

    # Count total matching records
    count_query = select(func.count()).select_from(base_query.subquery())
    total = db.scalar(count_query) or 0

    # Paginate and order by row_number
    page_query = base_query.order_by(Certificate.row_number).limit(limit).offset(offset)
    certificates = list(db.scalars(page_query).all())

    return total, certificates
