import time
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.models.certificate import Certificate
from app.models.enums import CertificateStatus, JobStatus
from app.models.job import GenerationJob
from app.services.job_processor import recover_interrupted_jobs


def test_recover_interrupted_jobs_on_startup(
    db_session: Session,
    test_session_factory: sessionmaker[Session],
    tmp_path: Path,
):
    """Seed interrupted jobs in DB, execute recover_interrupted_jobs, and verify completion."""
    with test_session_factory() as db:
        # Job 1: In PROCESSING state with 1 SUCCESS and 1 PENDING certificate
        job1 = GenerationJob(
            job_id="JOB-2026-RECOV001",
            event_name="Recovery Summit",
            event_date=date(2026, 10, 10),
            organization_name="Crash Recovery Inc",
            authorized_signatory="Recovery Lead",
            status=JobStatus.PROCESSING,
            total_recipients=2,
            request_hash="recov_hash_1",
        )
        c1_1 = Certificate(
            certificate_id="CERT-2026-REC1DONE",
            job_id=job1.job_id,
            row_number=1,
            recipient_name="Already Done User",
            recipient_email="done@example.com",
            status=CertificateStatus.SUCCESS,
            attempts=1,
        )
        c1_2 = Certificate(
            certificate_id="CERT-2026-REC1PEND",
            job_id=job1.job_id,
            row_number=2,
            recipient_name="Pending Recovery User",
            recipient_email="pending@example.com",
            status=CertificateStatus.PENDING,
            attempts=0,
        )
        job1.certificates = [c1_1, c1_2]

        # Job 2: Fully completed job (should NOT be picked up)
        job2 = GenerationJob(
            job_id="JOB-2026-RECOV002",
            event_name="Done Summit",
            event_date=date(2026, 10, 10),
            organization_name="Done Org",
            authorized_signatory="Done Signer",
            status=JobStatus.COMPLETED,
            total_recipients=1,
            request_hash="recov_hash_2",
        )
        c2_1 = Certificate(
            certificate_id="CERT-2026-REC2DONE",
            job_id=job2.job_id,
            row_number=1,
            recipient_name="Already Completed",
            recipient_email="completed@example.com",
            status=CertificateStatus.SUCCESS,
            attempts=1,
        )
        job2.certificates = [c2_1]

        db.add_all([job1, job2])
        db.commit()

    # Trigger recovery
    recovered_ids = recover_interrupted_jobs(test_session_factory)
    assert "JOB-2026-RECOV001" in recovered_ids
    assert "JOB-2026-RECOV002" not in recovered_ids

    # Allow recovery thread to execute
    max_wait = 10.0
    start = time.time()
    completed = False

    while time.time() - start < max_wait:
        with test_session_factory() as db:
            j1 = db.get(GenerationJob, "JOB-2026-RECOV001")
            if j1.status == JobStatus.COMPLETED:
                completed = True
                assert j1.processed_count == 2
                assert j1.successful_count == 2
                assert j1.failed_count == 0
                cert_pending = db.get(Certificate, "CERT-2026-REC1PEND")
                assert cert_pending.status == CertificateStatus.SUCCESS
                assert cert_pending.attempts == 1
                break
        time.sleep(0.1)

    assert completed, "Interrupted job was not finalized by recovery worker"
