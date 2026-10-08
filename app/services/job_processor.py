import logging
import threading
import time
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models.certificate import Certificate
from app.models.enums import CertificateStatus, FailureType, JobStatus
from app.models.job import GenerationJob
from app.services.certificate_generator import (
    CertificateDataError,
    generate_certificate_pdf,
)
from app.services.certificate_service import build_certificate_data
from app.services.job_service import recompute_counts
from app.services.storage import PdfStorage

logger = logging.getLogger("bulk_cert.processor")


def process_job(
    job_id: str,
    session_factory: sessionmaker[Session],
    storage: PdfStorage | None = None,
) -> None:
    """
    Background worker task that processes pending certificates for a job.
    Opens its own isolated database session and commits progress after each certificate.
    """
    settings = get_settings()
    if storage is None:
        storage = PdfStorage(root_dir=settings.STORAGE_DIR)

    with session_factory() as db:
        job = db.get(GenerationJob, job_id)
        if job is None:
            logger.warning("Job %s not found for processing", job_id)
            return

        # Advance job status from PENDING to PROCESSING
        if job.status == JobStatus.PENDING:
            job.status = JobStatus.PROCESSING
            db.commit()
            db.refresh(job)

        logger.info("Starting processing for job %s (total: %d)", job_id, job.total_recipients)

        # Batch iteration over PENDING certificates ordered by row_number
        while True:
            pending_ids = list(
                db.scalars(
                    select(Certificate.certificate_id)
                    .where(
                        Certificate.job_id == job_id,
                        Certificate.status == CertificateStatus.PENDING,
                    )
                    .order_by(Certificate.row_number)
                    .limit(50)
                ).all()
            )

            if not pending_ids:
                break

            for cert_id in pending_ids:
                cert = db.get(Certificate, cert_id)
                if cert is None or cert.status != CertificateStatus.PENDING:
                    continue

                cert.attempts += 1
                now = datetime.now(UTC)

                try:
                    # Demo failure switch support (Phase 7)
                    if (
                        settings.ENABLE_DEMO_FAILURES
                        and cert.recipient_name
                        and cert.recipient_name.upper().startswith("FAILME")
                        and cert.attempts == 1
                    ):
                        raise RuntimeError("Simulated transient failure (demo)")

                    data = build_certificate_data(cert, job)
                    pdf_bytes = generate_certificate_pdf(data)
                    rel_path = storage.save(
                        job_id=job.job_id,
                        cert_id=cert.certificate_id,
                        data=pdf_bytes,
                    )
                    cert.status = CertificateStatus.SUCCESS
                    cert.file_path = rel_path
                    cert.failure_type = None
                    cert.error_message = None
                    cert.completed_at = now
                    logger.info(
                        "Job %s | Cert %s (row %d) -> SUCCESS",
                        job_id,
                        cert.certificate_id,
                        cert.row_number,
                    )

                except CertificateDataError as cde:
                    cert.status = CertificateStatus.FAILED
                    cert.failure_type = FailureType.VALIDATION
                    cert.error_message = str(cde)[:500]
                    cert.completed_at = now
                    logger.warning(
                        "Job %s | Cert %s (row %d) -> FAILED (VALIDATION): %s",
                        job_id,
                        cert.certificate_id,
                        cert.row_number,
                        cde,
                    )

                except Exception as exc:
                    cert.status = CertificateStatus.FAILED
                    cert.failure_type = FailureType.GENERATION
                    cert.error_message = str(exc)[:500]
                    cert.completed_at = now
                    logger.exception(
                        "Job %s | Cert %s (row %d) -> FAILED (GENERATION): %s",
                        job_id,
                        cert.certificate_id,
                        cert.row_number,
                        exc,
                    )

                # Recompute counts and commit after every single certificate
                recompute_counts(db, job)
                db.commit()

                if settings.SIMULATED_DELAY_MS > 0:
                    time.sleep(settings.SIMULATED_DELAY_MS / 1000.0)

        # Final check: if no PENDING certificates remain, finalize the job
        remaining_pending = (
            db.scalar(
                select(func.count(Certificate.certificate_id)).where(
                    Certificate.job_id == job_id,
                    Certificate.status == CertificateStatus.PENDING,
                )
            )
            or 0
        )

        if remaining_pending == 0:
            recompute_counts(db, job)
            if job.failed_count == 0:
                job.status = JobStatus.COMPLETED
            elif job.successful_count > 0:
                job.status = JobStatus.COMPLETED_WITH_ERRORS
            else:
                job.status = JobStatus.FAILED

            job.completed_at = datetime.now(UTC)
            db.commit()
            logger.info(
                "Finalized job %s -> status: %s (success: %d, failed: %d)",
                job.job_id,
                job.status.value,
                job.successful_count,
                job.failed_count,
            )


def recover_interrupted_jobs(session_factory: sessionmaker[Session]) -> list[str]:
    """
    Find jobs in PENDING or PROCESSING states with unfinished certificates and
    launch background threads to finish them.
    Returns list of recovered job IDs.
    """
    with session_factory() as db:
        interrupted_job_ids = list(
            db.scalars(
                select(GenerationJob.job_id)
                .join(Certificate, Certificate.job_id == GenerationJob.job_id)
                .where(
                    GenerationJob.status.in_([JobStatus.PENDING, JobStatus.PROCESSING]),
                    Certificate.status == CertificateStatus.PENDING,
                )
                .distinct()
            ).all()
        )

    if interrupted_job_ids:
        logger.info(
            "Found %d interrupted jobs to recover: %s",
            len(interrupted_job_ids),
            interrupted_job_ids,
        )
        for job_id in interrupted_job_ids:
            thread = threading.Thread(
                target=process_job,
                args=(job_id, session_factory),
                daemon=True,
                name=f"recovery-worker-{job_id}",
            )
            thread.start()

    return interrupted_job_ids
